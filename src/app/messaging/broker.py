from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aio_pika import DeliveryMode, ExchangeType, Message, connect_robust
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue

from app.core.enums import Channel
from app.messaging.tasks import NotificationTask

EXCHANGE_NAME = "notifications"
QUEUE_NAMES = {channel: f"notifications.{channel.value}" for channel in Channel}


class Publisher:
    def __init__(self, exchange: AbstractExchange) -> None:
        self.exchange = exchange

    async def publish(self, task: NotificationTask) -> None:
        await self.exchange.publish(
            Message(
                body=task.model_dump_json().encode(),
                content_type="application/json",
                content_encoding="utf-8",
                delivery_mode=DeliveryMode.PERSISTENT,
                message_id=str(task.notification_id),
            ),
            routing_key=task.channel.value,
            mandatory=True,
            timeout=5,
        )


@dataclass(frozen=True)
class Broker:
    publisher: Publisher
    queues: dict[Channel, AbstractQueue]


async def declare_topology(channel: AbstractChannel) -> Broker:
    exchange = await channel.declare_exchange(EXCHANGE_NAME, ExchangeType.DIRECT, durable=True)
    queues = {}
    for notification_channel, name in QUEUE_NAMES.items():
        queue = await channel.declare_queue(name, durable=True)
        await queue.bind(exchange, routing_key=notification_channel.value)
        queues[notification_channel] = queue
    return Broker(publisher=Publisher(exchange), queues=queues)


@asynccontextmanager
async def connect_broker(url: str) -> AsyncIterator[Broker]:
    connection = await connect_robust(url, timeout=5)
    async with connection:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        async with channel:
            await channel.set_qos(prefetch_count=1)
            yield await declare_topology(channel)
