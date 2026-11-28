from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        CheckConstraint("reserved_balance >= 0", name="reserved_balance_non_negative"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    # Хранится только SHA-256 хэш ключа (64 символа hex), сам ключ не хранится
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        server_default=text("0.00"),
    )
    reserved_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        server_default=text("0.00"),
    )
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
