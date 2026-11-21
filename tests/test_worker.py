import asyncio
from unittest.mock import AsyncMock

import pytest
from aio_pika.abc import AbstractIncomingMessage
from asyncpg import PostgresError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.enums import Channel
from app.worker import handle_message


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"notification_id":0,"channel":"sms"}',
        b'{"notification_id":true,"channel":"sms"}',
        b'{"notification_id":"1","channel":"sms"}',
        b'{"notification_id":1,"channel":"fax"}',
        b'{"notification_id":1,"channel":"email"}',
        b'{"notification_id":1,"channel":"sms","extra":true}',
    ],
)
def test_invalid_task_is_rejected(body: bytes) -> None:
    message = AsyncMock(spec=AbstractIncomingMessage)
    message.body = body
    asyncio.run(handle_message(message, Channel.SMS, async_sessionmaker()))
    message.reject.assert_awaited_once_with(requeue=False)
    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()


@pytest.mark.parametrize(
    "error", [SQLAlchemyError(), PostgresError(), ConnectionRefusedError(), TimeoutError()]
)
def test_database_error_requeues_without_ack(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    message = AsyncMock(spec=AbstractIncomingMessage)
    message.body = b'{"notification_id":1,"channel":"sms"}'
    monkeypatch.setattr("app.worker.claim_notification", AsyncMock(side_effect=error))
    monkeypatch.setattr("app.worker.asyncio.sleep", AsyncMock())
    asyncio.run(handle_message(message, Channel.SMS, async_sessionmaker()))
    message.nack.assert_awaited_once_with(requeue=True)
    message.ack.assert_not_awaited()
    message.reject.assert_not_awaited()
