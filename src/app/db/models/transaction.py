from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import TransactionType
from app.db.base import Base, str_enum


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("balance_after >= 0", name="balance_after_non_negative"),
        Index("ix_transactions_shop_id_created_at", "shop_id", "created_at"),
        Index("ix_transactions_notification_id", "notification_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shops.id"))
    notification_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("notifications.id"),
    )
    type: Mapped[TransactionType] = mapped_column(str_enum(TransactionType))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
