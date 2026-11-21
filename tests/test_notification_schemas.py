from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.notifications.schemas import NotificationCreate

adapter = TypeAdapter(NotificationCreate)


@pytest.mark.parametrize(
    "payload",
    [
        {"channel": "fax", "recipient": "+79990000000", "body": "Order"},
        {"channel": "sms", "recipient": "79990000000", "body": "Order"},
        {"channel": "sms", "recipient": "+09990000000", "body": "Order"},
        {"channel": "sms", "recipient": "+79990000000", "body": "x" * 161},
        {"channel": "sms", "recipient": "+79990000000", "body": "   "},
        {"channel": "sms", "recipient": "+79990000000", "body": "Order", "title": "Hi"},
        {"channel": "email", "recipient": "invalid", "subject": "Order", "body": "Hi"},
        {"channel": "email", "recipient": "user@example.com", "body": "Hi"},
        {"channel": "push", "recipient": "device", "body": "Hi"},
        {"channel": "push", "recipient": " ", "title": "Order", "body": "Hi"},
        {"channel": "push", "recipient": "x" * 321, "title": "Order", "body": "Hi"},
    ],
)
def test_invalid_message_is_rejected(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)


def test_message_values_are_preserved() -> None:
    message = adapter.validate_python(
        {
            "channel": "email",
            "recipient": "User@EXAMPLE.com",
            "subject": " Заказ ",
            "body": " Hi ",
        }
    )
    assert message.recipient == "User@EXAMPLE.com"
    assert message.body == " Hi "
