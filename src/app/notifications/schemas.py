from datetime import datetime
from typing import Annotated, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.notifications.statuses import NotificationStatus


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str

    @field_validator("body", "recipient", "subject", "title", check_fields=False)
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        if "\x00" in value:
            raise ValueError("Must not contain a null character")
        return value


class EmailMessage(Message):
    channel: Literal["email"]
    recipient: Annotated[str, Field(min_length=3, max_length=254)]
    subject: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=10000)]

    @field_validator("recipient")
    @classmethod
    def validate_email(cls, value: str) -> str:
        try:
            validate_email(value, check_deliverability=False)
        except EmailNotValidError as exc:
            raise ValueError("Invalid email address") from exc
        return value


class SmsMessage(Message):
    channel: Literal["sms"]
    recipient: Annotated[str, Field(pattern=r"^\+[1-9][0-9]{1,14}$")]
    body: Annotated[str, Field(min_length=1, max_length=160)]


class PushMessage(Message):
    channel: Literal["push"]
    recipient: Annotated[str, Field(min_length=1, max_length=320)]
    title: Annotated[str, Field(min_length=1, max_length=100)]
    body: Annotated[str, Field(min_length=1, max_length=1000)]


NotificationCreate = Annotated[
    EmailMessage | SmsMessage | PushMessage, Field(discriminator="channel")
]


class NotificationResponse(BaseModel):
    id: int
    message: NotificationCreate
    status: NotificationStatus
    created_at: datetime
    updated_at: datetime
