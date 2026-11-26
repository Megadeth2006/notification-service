import json
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Channel
from app.db.models.notification import Notification
from app.db.models.outbox_event import OutboxEvent
from app.messaging.tasks import NotificationTask
from app.notifications.schemas import (
    EmailMessage,
    NotificationCreate,
    NotificationResponse,
    PushMessage,
    SmsMessage,
)
from app.notifications.statuses import NotificationStatus


def notification_response(notification: Notification) -> NotificationResponse:
    message: EmailMessage | SmsMessage | PushMessage
    match notification.channel:
        case Channel.EMAIL:
            message = EmailMessage(
                channel="email",
                recipient=notification.recipient,
                subject=notification.subject or "",
                body=notification.content,
            )
        case Channel.PUSH:
            message = PushMessage(
                channel="push",
                recipient=notification.recipient,
                title=notification.subject or "",
                body=notification.content,
            )
        case Channel.SMS:
            message = SmsMessage(
                channel="sms",
                recipient=notification.recipient,
                body=notification.content,
            )
    return NotificationResponse(
        id=notification.id,
        message=message,
        status=notification.status,
        created_at=notification.created_at,
        updated_at=notification.updated_at,
    )


async def create_notification(
    session: AsyncSession,
    shop_id: int,
    message: NotificationCreate,
    idempotency_key: str,
) -> tuple[NotificationResponse, bool]:
    payload = json.dumps(
        message.model_dump(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_hash = sha256(payload.encode()).hexdigest()
    subject = (
        message.subject
        if isinstance(message, EmailMessage)
        else (message.title if isinstance(message, PushMessage) else None)
    )
    statement = (
        insert(Notification)
        .values(
            shop_id=shop_id,
            channel=Channel(message.channel),
            recipient=message.recipient,
            subject=subject,
            content=message.body,
            status=NotificationStatus.CREATED,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        .on_conflict_do_nothing(constraint="uq_notifications_shop_id_idempotency_key")
        .returning(Notification)
    )
    notification = (await session.scalars(statement)).one_or_none()
    created = notification is not None
    if notification is not None:
        task = NotificationTask(notification_id=notification.id, channel=notification.channel)
        session.add(
            OutboxEvent(
                notification_id=notification.id,
                payload=task.model_dump(mode="json"),
            )
        )
    if notification is None:
        notification = (
            await session.scalars(
                select(Notification).where(
                    Notification.shop_id == shop_id,
                    Notification.idempotency_key == idempotency_key,
                )
            )
        ).one()
        if notification.request_hash != request_hash:
            raise HTTPException(status_code=409, detail="Idempotency key has a different request")
    result = notification_response(notification)
    await session.commit()
    return result, created


async def get_notification(
    session: AsyncSession,
    shop_id: int,
    notification_id: int,
) -> NotificationResponse:
    notification = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.shop_id == shop_id,
        )
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification_response(notification)
