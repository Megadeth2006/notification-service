import argparse
import asyncio
import logging
from contextlib import suppress

from aio_pika.abc import AbstractIncomingMessage
from aio_pika.exceptions import AMQPException, ChannelInvalidStateError
from asyncpg import PostgresError
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.core.enums import Channel
from app.db.models.notification import Notification
from app.db.session import get_engine
from app.messaging.broker import connect_broker
from app.messaging.tasks import NotificationTask
from app.notifications.statuses import NotificationStatus

logger = logging.getLogger(__name__)


async def claim_notification(
    sessions: async_sessionmaker[AsyncSession],
    task: NotificationTask,
) -> bool:
    async with sessions.begin() as session:
        notification_id = await session.scalar(
            update(Notification)
            .where(
                Notification.id == task.notification_id,
                Notification.channel == task.channel,
                Notification.status.in_([NotificationStatus.CREATED, NotificationStatus.QUEUED]),
            )
            .values(status=NotificationStatus.SENDING)
            .returning(Notification.id)
        )
    return notification_id is not None


async def handle_message(
    message: AbstractIncomingMessage,
    channel: Channel,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    try:
        task = NotificationTask.model_validate_json(message.body)
        if task.channel != channel:
            raise ValueError("Task channel does not match queue")
    except (ValidationError, ValueError):
        logger.warning("Rejected invalid notification task")
        await message.reject(requeue=False)
        return
    try:
        claimed = await claim_notification(sessions, task)
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError):
        logger.exception("Notification task could not be committed")
        await asyncio.sleep(1)
        await message.nack(requeue=True)
        return
    if claimed:
        logger.info("Notification %s is sending", task.notification_id)
    await message.ack()


async def run(channel: Channel) -> None:
    engine = get_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with (
            connect_broker(get_settings().rabbitmq_url) as broker,
            broker.queues[channel].iterator() as messages,
        ):
            async for message in messages:
                try:
                    await handle_message(message, channel, sessions)
                except (AMQPException, ChannelInvalidStateError, OSError, TimeoutError):
                    logger.exception("Task acknowledgement failed; waiting for redelivery")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("channel", choices=[channel.value for channel in Channel])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with suppress(KeyboardInterrupt):
        asyncio.run(run(Channel(args.channel)))
