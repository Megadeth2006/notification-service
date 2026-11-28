from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ShopName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class ShopCreate(BaseModel):
    name: ShopName

    @field_validator("name")
    @classmethod
    def reject_null_bytes(cls, value: str) -> str:
        # Отклоняем нуль байты, иначе упадет postgres.
        if "\x00" in value:
            raise ValueError("Null bytes are not allowed")
        return value


class ShopCreatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    api_key: str
    is_active: bool
    created_at: datetime


class ShopBalanceTopUp(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)


class ShopMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    balance: Decimal
    reserved_balance: Decimal
