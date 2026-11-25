import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.models.shop import Shop
from app.db.session import get_session
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    schema = f"test_shops_{uuid4().hex}"
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
            session.add(
                Shop(
                    name="Inactive",
                    api_key_hash=sha256(b"inactive-key").hexdigest(),
                    is_active=False,
                )
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


def test_register_shop_saves_only_key_hash(client: TestClient) -> None:
    response = client.post("/shops", json={"name": "  Test Shop  "})

    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["name"] == "Test Shop"
    assert data["api_key"].startswith("ntf_")
    assert data["is_active"] is True
    assert "created_at" in data

    async def fetch_shop() -> Shop | None:
        session_provider = app.dependency_overrides[get_session]
        async for session in session_provider():
            db_session: AsyncSession = session
            return await db_session.scalar(select(Shop).where(Shop.id == data["id"]))
        raise AssertionError("Session was not provided")

    shop = asyncio.run(fetch_shop())
    assert shop is not None
    assert shop.name == "Test Shop"
    assert shop.api_key_hash == sha256(data["api_key"].encode()).hexdigest()
    assert shop.api_key_hash != data["api_key"]


def test_registered_shop_can_access_protected_endpoint(client: TestClient) -> None:
    created = client.post("/shops", json={"name": "Active Shop"})
    assert created.status_code == 201
    api_key = created.json()["api_key"]

    response = client.post(
        "/notifications",
        json={"channel": "sms", "recipient": "+79990000000", "body": "Order paid"},
        headers={"X-API-Key": api_key, "Idempotency-Key": "order-1"},
    )
    assert response.status_code == 202


def test_register_multiple_shops_generates_unique_keys(client: TestClient) -> None:
    first = client.post("/shops", json={"name": "Same Name"})
    second = client.post("/shops", json={"name": "Same Name"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["api_key"] != second.json()["api_key"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 256},
        {"name": "bad\x00name"},
    ],
)
def test_register_shop_rejects_invalid_name(client: TestClient, payload: dict[str, str]) -> None:
    response = client.post("/shops", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-API-Key": "wrong-key"}, {"X-API-Key": "inactive-key"}],
)
def test_protected_endpoint_rejects_invalid_auth(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get("/notifications/1", headers=headers)
    assert response.status_code == 401
