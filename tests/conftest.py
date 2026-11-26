import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.models.shop import Shop
from app.db.session import get_session
from app.main import app


@pytest.fixture
def sessions() -> Iterator[async_sessionmaker[AsyncSession]]:
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

    async def teardown() -> None:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()

    asyncio.run(setup())
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        asyncio.run(teardown())


@pytest.fixture
def client(sessions: async_sessionmaker[AsyncSession]) -> Iterator[TestClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def rabbitmq_url() -> str:
    url = os.environ.get("TEST_RABBITMQ_URL")
    if not url:
        pytest.skip("Set TEST_RABBITMQ_URL to run RabbitMQ integration tests")
    return url
