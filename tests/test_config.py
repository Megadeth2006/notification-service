from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED: dict[str, Any] = {
    "postgres_user": "user",
    "postgres_password": "p@ss/word",
    "postgres_db": "db",
    "rabbitmq_user": "mq",
    "rabbitmq_password": "mq-pass",
}


def test_urls_are_built_from_parts() -> None:
    settings = Settings.model_validate(REQUIRED)

    assert settings.database_url == ("postgresql+asyncpg://user:p%40ss%2Fword@localhost:5432/db")
    assert settings.rabbitmq_url == "amqp://mq:mq-pass@localhost:5672/"


def test_missing_required_settings_fail_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # в пустой папке нет .env
    for name in REQUIRED:
        monkeypatch.delenv(name.upper(), raising=False)

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
