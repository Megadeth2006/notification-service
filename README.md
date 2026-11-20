# notification-service

Сервис уведомлений для интернет-магазина: принимает запросы по API и доставляет уведомления клиентам по каналам email, sms и push через несколько провайдеров.

## Быстрый старт

Требуется Python 3.12+ и [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pre-commit install
uv run uvicorn app.main:app --reload
```

Проверка: http://localhost:8000/health, документация API: http://localhost:8000/docs

## Проверки качества кода

```bash
uv run ruff check .          # линтер
uv run ruff format .         # форматирование
uv run mypy                  # проверка типов
uv run pytest                # тесты
uv run pre-commit run --all-files   # все проверки сразу
```

Хуки pre-commit запускаются автоматически при `git commit`. Если ruff
переформатировал файлы, сделайте `git add .` и повторите коммит.