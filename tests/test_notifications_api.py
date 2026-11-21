import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.models.notification import Notification
from app.db.models.shop import Shop
from app.db.session import get_session
from app.main import app
from app.notifications.statuses import NotificationStatus

HEADERS = {"X-API-Key": "shop-one", "Idempotency-Key": "order-123"}
SMS: dict[str, Any] = {"channel": "sms", "recipient": "+79990000000", "body": "Заказ принят"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    schema = f"test_notifications_{uuid4().hex}"
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )

    async def setup() -> None:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncSession(engine) as session:
            session.add_all(
                [
                    Shop(name="One", api_key_hash=sha256(b"shop-one").hexdigest()),
                    Shop(name="Two", api_key_hash=sha256(b"shop-two").hexdigest()),
                    Shop(
                        name="Inactive",
                        api_key_hash=sha256(b"inactive").hexdigest(),
                        is_active=False,
                    ),
                ]
            )
            await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    async def teardown() -> None:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()

    asyncio.run(setup())
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)
        asyncio.run(teardown())


@pytest.mark.parametrize(
    "message",
    [
        SMS,
        {"channel": "email", "recipient": "buyer@example.com", "subject": "Заказ", "body": "Hi"},
        {"channel": "push", "recipient": "device-token", "title": "Заказ", "body": "Hi"},
    ],
)
def test_create_and_get_notification(client: TestClient, message: dict[str, Any]) -> None:
    response = client.post("/notifications", json=message, headers=HEADERS)
    assert response.status_code == 202
    result = response.json()
    assert result["message"] == message
    assert result["status"] == "created"
    assert isinstance(result["id"], int)
    saved = client.get(response.headers["Location"], headers=HEADERS)
    assert saved.status_code == 200
    assert saved.json() == result


def test_get_returns_current_database_status(client: TestClient) -> None:
    notification_id = client.post("/notifications", json=SMS, headers=HEADERS).json()["id"]

    async def change_status() -> None:
        session_provider = app.dependency_overrides[get_session]
        async for session in session_provider():
            await session.execute(
                update(Notification)
                .where(Notification.id == notification_id)
                .values(status=NotificationStatus.SENDING)
            )
            await session.commit()

    asyncio.run(change_status())
    response = client.get(f"/notifications/{notification_id}", headers=HEADERS)
    assert response.json()["status"] == "sending"


def test_other_shop_cannot_read_notification(client: TestClient) -> None:
    response = client.post("/notifications", json=SMS, headers=HEADERS)
    for path in [response.headers["Location"], "/notifications/9223372036854775807"]:
        hidden = client.get(path, headers={"X-API-Key": "shop-two"})
        assert hidden.status_code == 404
        assert hidden.json() == {"detail": "Notification not found"}


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "bad"}, {"X-API-Key": "inactive"}])
def test_authentication_is_required(client: TestClient, headers: dict[str, str]) -> None:
    assert client.get("/notifications/1", headers=headers).status_code == 401
    assert (
        client.post(
            "/notifications",
            json=SMS,
            headers={
                **headers,
                "Idempotency-Key": "key",
            },
        ).status_code
        == 401
    )


def test_invalid_request_does_not_use_idempotency_key(client: TestClient) -> None:
    response = client.post("/notifications", json={**SMS, "recipient": "invalid"}, headers=HEADERS)
    assert response.status_code == 422
    assert client.post("/notifications", json=SMS, headers=HEADERS).status_code == 202


@pytest.mark.parametrize(
    ("message", "field"),
    [
        (SMS, "body"),
        (
            {
                "channel": "email",
                "recipient": "buyer@example.com",
                "subject": "Order",
                "body": "Hi",
            },
            "body",
        ),
        (
            {
                "channel": "email",
                "recipient": "buyer@example.com",
                "subject": "Order",
                "body": "Hi",
            },
            "subject",
        ),
        (
            {
                "channel": "email",
                "recipient": "buyer@example.com",
                "subject": "Order",
                "body": "Hi",
            },
            "recipient",
        ),
        ({"channel": "sms", "recipient": "+79990000000", "body": "Hi"}, "recipient"),
        ({"channel": "push", "recipient": "device-token", "title": "Order", "body": "Hi"}, "body"),
        ({"channel": "push", "recipient": "device-token", "title": "Order", "body": "Hi"}, "title"),
        (
            {"channel": "push", "recipient": "device-token", "title": "Order", "body": "Hi"},
            "recipient",
        ),
    ],
)
def test_null_character_does_not_use_idempotency_key(
    client: TestClient, message: dict[str, Any], field: str
) -> None:
    invalid_message = {**message, field: f"{message[field]}\x00"}
    response = client.post("/notifications", json=invalid_message, headers=HEADERS)
    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])
    created = client.post("/notifications", json=message, headers=HEADERS)
    assert created.status_code == 202
    saved = client.get(created.headers["Location"], headers=HEADERS)
    assert saved.status_code == 200
    assert saved.json()["message"] == message


@pytest.mark.parametrize("key", [None, "", "with space", "x" * 129])
def test_invalid_idempotency_key(client: TestClient, key: str | None) -> None:
    headers = {"X-API-Key": "shop-one"}
    if key is not None:
        headers["Idempotency-Key"] = key
    assert client.post("/notifications", json=SMS, headers=headers).status_code == 422


def test_idempotent_replay_and_conflict(client: TestClient) -> None:
    first = client.post("/notifications", json=SMS, headers=HEADERS)
    replay = client.post("/notifications", json=dict(reversed(list(SMS.items()))), headers=HEADERS)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    conflict = client.post("/notifications", json={**SMS, "body": "Different"}, headers=HEADERS)
    assert conflict.status_code == 409
    second_shop = client.post(
        "/notifications", json=SMS, headers={**HEADERS, "X-API-Key": "shop-two"}
    )
    assert second_shop.status_code == 202
    assert second_shop.json()["id"] != first.json()["id"]


def test_concurrent_replays_create_one_notification(client: TestClient) -> None:
    def create() -> tuple[int, int]:
        response = client.post("/notifications", json=SMS, headers=HEADERS)
        return response.status_code, response.json()["id"]

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: create(), range(6)))
    assert sorted(code for code, _ in results) == [200, 200, 200, 200, 200, 202]
    assert len({notification_id for _, notification_id in results}) == 1

    async def count_notifications() -> int:
        session_provider = app.dependency_overrides[get_session]
        async for session in session_provider():
            return int(await session.scalar(select(func.count()).select_from(Notification)))
        raise AssertionError("Session was not provided")

    assert asyncio.run(count_notifications()) == 1


@pytest.mark.parametrize("notification_id", ["invalid", "0", "-1", str(2**63)])
def test_invalid_notification_id(client: TestClient, notification_id: str) -> None:
    assert client.get(f"/notifications/{notification_id}", headers=HEADERS).status_code == 422
