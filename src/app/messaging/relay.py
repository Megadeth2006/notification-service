import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime

from aio_pika.exceptions import AMQPException, ChannelInvalidStateError
from asyncpg import PostgresError
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models.notification import Notification
from app.db.models.outbox_event import OutboxEvent
from app.db.session import get_engine
from app.messaging.broker import Publisher, connect_broker
from app.messaging.tasks import NotificationTask
from app.notifications.statuses import NotificationStatus

logger = logging.getLogger(__name__)


async def publish_next(
    sessions: async_sessionmaker[AsyncSession],
    publisher: Publisher,
) -> bool:
    async with sessions.begin() as session:
        event = await session.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            return False
        task = NotificationTask.model_validate(event.payload)
        if task.notification_id != event.notification_id:
            raise ValueError(f"Outbox event {event.id} has a different notification ID")
        await session.execute(
            update(Notification)
            .where(
                Notification.id == task.notification_id,
                Notification.status == NotificationStatus.CREATED,
            )
            .values(status=NotificationStatus.QUEUED)
        )
        await publisher.publish(task)
        event.published_at = datetime.now(UTC)
    return True


async def run() -> None:
    engine = get_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with connect_broker(get_settings().rabbitmq_url) as broker:
            while True:
                try:
                    if await publish_next(sessions, broker.publisher):
                        continue
                except (
                    AMQPException,
                    ChannelInvalidStateError,
                    OSError,
                    TimeoutError,
                    SQLAlchemyError,
                    PostgresError,
                ):
                    logger.exception("Outbox publication failed")
                await asyncio.sleep(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with suppress(KeyboardInterrupt):
        asyncio.run(run())
