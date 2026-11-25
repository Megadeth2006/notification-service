from sqlalchemy import BigInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Channel
from app.db.base import Base, str_enum


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    channel: Mapped[Channel] = mapped_column(str_enum(Channel))
    priority: Mapped[int]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
