from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AttemptResult
from app.db.base import Base, str_enum


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint(
            "notification_id",
            "attempt_number",
            name="uq_delivery_attempts_notification_id_attempt_number",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notification_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("notifications.id"))
    provider_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("providers.id"))
    attempt_number: Mapped[int]
    result: Mapped[AttemptResult] = mapped_column(str_enum(AttemptResult))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
