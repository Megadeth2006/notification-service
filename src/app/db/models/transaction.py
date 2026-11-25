from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import TransactionType
from app.db.base import Base, str_enum


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_shop_id_created_at", "shop_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shops.id"))
    type: Mapped[TransactionType] = mapped_column(str_enum(TransactionType))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
