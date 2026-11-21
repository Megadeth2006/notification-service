import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

# Единые имена индексов и ограничений: без них Alembic генерирует
# случайные имена, и потом их неудобно менять
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Python-тип -> тип в БД: все даты с часовым поясом, словари как JSONB
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
    }


def str_enum(enum_cls: type[enum.Enum], length: int = 20) -> Enum:
    """Enum, который хранится в БД обычной строкой (VARCHAR).

    Нативные enum'ы Postgres неудобно менять миграциями, строка проще.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )
