import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from aio_pika import DeliveryMode
from aio_pika.abc import AbstractIncomingMessage
from aio_pika.exceptions import AMQPException
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.core.enums import Channel
from app.db.models.notification import Notification
from app.db.models.outbox_event import OutboxEvent
from app.messaging.broker import Broker, Publisher, connect_broker
from app.messaging.relay import publish_next
from app.messaging.tasks import NotificationTask
from app.notifications.statuses import NotificationStatus
from app.worker import claim_notification, handle_message

HEADERS = {"X-API-Key": "shop-one", "Idempotency-Key": "order-123"}
SMS = {"channel": "sms", "recipient": "+79990000000", "body": "Order"}


@asynccontextmanager
async def isolated_broker(url: str) -> AsyncIterator[Broker]:
    async with connect_broker(url) as broker:
        for queue in broker.queues.values():
            await queue.purge()
        try:
            yield broker
        finally:
            for queue in broker.queues.values():
                await queue.purge()


def test_api_creates_one_outbox_event(
    client: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    notification_id = client.post("/notifications", json=SMS, headers=HEADERS).json()["id"]
    assert client.post("/notifications", json=SMS, headers=HEADERS).status_code == 200
    assert (
        client.post("/notifications", json={**SMS, "body": "Other"}, headers=HEADERS).status_code
        == 409
    )

    async def check() -> None:
        async with sessions() as session:
            events = (await session.scalars(select(OutboxEvent))).all()
            assert len(events) == 1
            assert events[0].notification_id == notification_id
            assert events[0].payload == {"notification_id": notification_id, "channel": "sms"}
            assert events[0].published_at is None

    asyncio.run(check())


def test_outbox_failure_rolls_back_notification(
    client: TestClient,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    def fail_outbox(session: Session, flush_context: object, instances: object) -> None:
        if any(isinstance(item, OutboxEvent) for item in session.new):
            raise RuntimeError("Outbox write failed")

    event.listen(Session, "before_flush", fail_outbox)
    try:
        with pytest.raises(RuntimeError, match="Outbox write failed"):
            client.post("/notifications", json=SMS, headers=HEADERS)
    finally:
        event.remove(Session, "before_flush", fail_outbox)

    async def check() -> None:
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Notification)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 0

    asyncio.run(check())
    assert client.post("/notifications", json=SMS, headers=HEADERS).status_code == 202


def test_concurrent_claims_change_status_once(
    client: TestClient,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    notification_id = client.post("/notifications", json=SMS, headers=HEADERS).json()["id"]
    task = NotificationTask(notification_id=notification_id, channel=Channel.SMS)

    async def check() -> None:
        results = await asyncio.gather(*(claim_notification(sessions, task) for _ in range(6)))
        assert sum(results) == 1
        async with sessions() as session:
            assert await session.scalar(select(Notification.status)) == NotificationStatus.SENDING

    asyncio.run(check())


def test_parallel_relays_skip_locked_events(
    client: TestClient,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first_id = client.post("/notifications", json=SMS, headers=HEADERS).json()["id"]
    second_id = client.post(
        "/notifications",
        json=SMS,
        headers={
            **HEADERS,
            "Idempotency-Key": "order-124",
        },
    ).json()["id"]

    async def check() -> None:
        locked = asyncio.Event()
        release = asyncio.Event()

        async def block_first(task: NotificationTask) -> None:
            assert task.notification_id == first_id
            locked.set()
            await release.wait()

        first_publisher = AsyncMock(spec=Publisher)
        first_publisher.publish.side_effect = block_first
        second_publisher = AsyncMock(spec=Publisher)
        first_relay = asyncio.create_task(publish_next(sessions, first_publisher))
        try:
            await asyncio.wait_for(locked.wait(), timeout=5)
            assert await asyncio.wait_for(publish_next(sessions, second_publisher), timeout=5)
            second_publisher.publish.assert_awaited_once_with(
                NotificationTask(
                    notification_id=second_id,
                    channel=Channel.SMS,
                )
            )
        finally:
            release.set()
            await first_relay
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(
                        OutboxEvent.published_at.is_not(None),
                    )
                )
                == 2
            )

    asyncio.run(check())


@pytest.mark.parametrize(
    "status", [NotificationStatus.SENDING, NotificationStatus.DELIVERED, NotificationStatus.FAILED]
)
def test_duplicate_is_acked_without_changing_status(
    client: TestClient,
    sessions: async_sessionmaker[AsyncSession],
    status: NotificationStatus,
) -> None:
    notification_id = client.post("/notifications", json=SMS, headers=HEADERS).json()["id"]
    task = NotificationTask(notification_id=notification_id, channel=Channel.SMS)
    message = AsyncMock(spec=AbstractIncomingMessage)
    message.body = task.model_dump_json().encode()

    async def check() -> None:
        async with sessions.begin() as session:
            await session.execute(update(Notification).values(status=status))
        await handle_message(message, Channel.SMS, sessions)
        async with sessions() as session:
            assert await session.scalar(select(Notification.status)) == status
        message.ack.assert_awaited_once_with()
        message.nack.assert_not_awaited()

    asyncio.run(check())


def test_ack_happens_after_commit(
    client: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    notification_id = client.post("/notifications", json=SMS, headers=HEADERS).json()["id"]
    message = AsyncMock(spec=AbstractIncomingMessage)
    message.body = (
        NotificationTask(notification_id=notification_id, channel=Channel.SMS)
        .model_dump_json()
        .encode()
    )

    async def check_commit() -> None:
        async with sessions() as session:
            assert await session.scalar(select(Notification.status)) == NotificationStatus.SENDING

    message.ack.side_effect = check_commit
    asyncio.run(handle_message(message, Channel.SMS, sessions))
    message.ack.assert_awaited_once_with()


def test_all_channels_are_routed_to_their_queues(rabbitmq_url: str) -> None:
    async def check() -> None:
        async with isolated_broker(rabbitmq_url) as broker:
            for notification_id, channel in enumerate(Channel, start=1):
                await broker.publisher.publish(
                    NotificationTask(notification_id=notification_id, channel=channel)
                )
            for notification_id, channel in enumerate(Channel, start=1):
                message = await broker.queues[channel].get(timeout=5)
                assert message is not None
                assert message.delivery_mode == DeliveryMode.PERSISTENT
                assert message.message_id == str(notification_id)
                assert NotificationTask.model_validate_json(message.body) == NotificationTask(
                    notification_id=notification_id, channel=channel
                )
                await message.ack()
                assert await broker.queues[channel].get(fail=False) is None

    asyncio.run(check())


@pytest.mark.parametrize("channel", list(Channel))
def test_api_relay_worker_flow(
    client: TestClient,
    sessions: async_sessionmaker[AsyncSession],
    rabbitmq_url: str,
    channel: Channel,
) -> None:
    messages = {
        Channel.SMS: SMS,
        Channel.EMAIL: {
            "channel": "email",
            "recipient": "buyer@example.com",
            "subject": "Order",
            "body": "Hi",
        },
        Channel.PUSH: {"channel": "push", "recipient": "device", "title": "Order", "body": "Hi"},
    }
    response = client.post("/notifications", json=messages[channel], headers=HEADERS)
    assert response.status_code == 202

    async def check() -> None:
        async with isolated_broker(rabbitmq_url) as broker:
            assert await publish_next(sessions, broker.publisher)
            async with sessions() as session:
                assert (
                    await session.scalar(select(Notification.status)) == NotificationStatus.QUEUED
                )
                assert await session.scalar(select(OutboxEvent.published_at)) is not None
            message = await broker.queues[channel].get(timeout=5)
            assert message is not None
            await handle_message(message, channel, sessions)
            assert not await publish_next(sessions, broker.publisher)

    asyncio.run(check())
    assert client.get(response.headers["Location"], headers=HEADERS).json()["status"] == "sending"


def test_unroutable_publish_keeps_outbox_pending(
    client: TestClient,
    sessions: async_sessionmaker[AsyncSession],
    rabbitmq_url: str,
) -> None:
    client.post("/notifications", json=SMS, headers=HEADERS)

    async def check() -> None:
        async with isolated_broker(rabbitmq_url) as broker:
            queue = broker.queues[Channel.SMS]
            await queue.unbind(broker.publisher.exchange, routing_key="sms")
            try:
                with pytest.raises(AMQPException):
                    await publish_next(sessions, broker.publisher)
                async with sessions() as session:
                    assert await session.scalar(select(OutboxEvent.published_at)) is None
                    assert (
                        await session.scalar(select(Notification.status))
                        == NotificationStatus.CREATED
                    )
            finally:
                await queue.bind(broker.publisher.exchange, routing_key="sms")
            assert await publish_next(sessions, broker.publisher)

    asyncio.run(check())


def test_publish_before_commit_failure_is_safe_to_repeat(
    client: TestClient,
    sessions: async_sessionmaker[AsyncSession],
    rabbitmq_url: str,
) -> None:
    client.post("/notifications", json=SMS, headers=HEADERS)

    async def check() -> None:
        async with isolated_broker(rabbitmq_url) as broker:

            async def publish_then_fail(task: NotificationTask) -> None:
                await broker.publisher.publish(task)
                raise TimeoutError("Confirmation lost")

            publisher = AsyncMock(spec=Publisher)
            publisher.publish.side_effect = publish_then_fail
            with pytest.raises(TimeoutError):
                await publish_next(sessions, publisher)
            async with sessions() as session:
                assert await session.scalar(select(OutboxEvent.published_at)) is None
            queue = broker.queues[Channel.SMS]
            first = await queue.get(timeout=5)
            assert first is not None
            await handle_message(first, Channel.SMS, sessions)
            async with sessions() as session:
                updated_at = await session.scalar(select(Notification.updated_at))
            assert await publish_next(sessions, broker.publisher)
            second = await queue.get(timeout=5)
            assert second is not None
            await handle_message(second, Channel.SMS, sessions)
            async with sessions() as session:
                assert (
                    await session.scalar(select(Notification.status)) == NotificationStatus.SENDING
                )
                assert await session.scalar(select(Notification.updated_at)) == updated_at
                assert await session.scalar(select(OutboxEvent.published_at)) is not None

    asyncio.run(check())
