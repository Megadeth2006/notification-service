from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Channel
from app.db.base import Base, str_enum
from app.notifications.statuses import NotificationStatus


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "idempotency_key",
            name="uq_notifications_shop_id_idempotency_key",
        ),
        Index("ix_notifications_shop_id_created_at", "shop_id", "created_at"),
        Index("ix_notifications_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shops.id"))
    channel: Mapped[Channel] = mapped_column(str_enum(Channel))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus),
        server_default=NotificationStatus.CREATED.value,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    # Хэш тела запроса: нужен, чтобы отличить повтор от конфликта (409)
    request_hash: Mapped[str] = mapped_column(String(64))
    cost: Mapped[int] = mapped_column(BigInteger, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
