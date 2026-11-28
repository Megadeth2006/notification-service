# notification-service

Сервис уведомлений для интернет-магазина: принимает запросы по API и доставляет уведомления клиентам по каналам email, sms и push через несколько провайдеров.

## Быстрый старт

Требуется Python 3.12+ и [uv](https://docs.astral.sh/uv/) и Docker.

```bash
cp .env.example .env                # задайте свои пароли
uv sync
uv run pre-commit install
docker compose up -d                # PostgreSQL и RabbitMQ
uv run alembic upgrade head         # миграции
```

## Запуск

Каждый процесс в отдельном терминале, из корня проекта:

```bash
uv run uvicorn app.main:app --reload    # API
uv run python -m app.messaging.relay    # публикация outbox в RabbitMQ
uv run python -m app.worker email       # воркеры по каналам
uv run python -m app.worker sms
uv run python -m app.worker push
```

- API и документация: http://localhost:8000/docs
- Проверка: http://localhost:8000/health
- Панель RabbitMQ: http://localhost:15672 (логин и пароль из `.env`)

## Тесты

```bash
uv run pytest
```

Интеграционным тестам нужны тестовые PostgreSQL и RabbitMQ, без них они пропускаются. Подробности: [docs/testing.md](docs/testing.md).

## Документация

| Файл | О чём |
|---|---|
| [docs/api.md](docs/api.md) | API уведомлений, идемпотентность, форматы каналов |
| [docs/messaging.md](docs/messaging.md) | очереди, relay, воркер, гарантии доставки |
| [docs/testing.md](docs/testing.md) | как запускать интеграционные тесты |
| [CONTRIBUTING.md](CONTRIBUTING.md) | правила работы, проверки качества, CI |

## Настройки

Все настройки задаются переменными окружения, образец лежит в `.env.example`. Логины и пароли обязательны: без них приложение и `docker compose` не стартуют.

## Миграции

```bash
uv run alembic upgrade head                              #применить миграции
uv run alembic revision --autogenerate -m "description"     # создать миграцию по моделям
uv run alembic downgrade -1                              # откатить последнюю
```
