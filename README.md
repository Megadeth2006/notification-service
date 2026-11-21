# notification-service

Сервис уведомлений для интернет-магазина: принимает запросы по API и доставляет уведомления клиентам по каналам email, sms и push через несколько провайдеров.

## Быстрый старт

Требуется Python 3.12+ и [uv](https://docs.astral.sh/uv/) и Docker.

```bash
cp .env.example .env
uv sync
uv run pre-commit install
docker compose up -d                # PostgreSQL и RabbitMQ
uv run uvicorn app.main:app --reload
```

Проверка: http://localhost:8000/health, документация API: http://localhost:8000/docs

Панель RabbitMQ: http://localhost:15672 (логин и пароль из `.env`).

## Уведомления

`POST /notifications` принимает сообщение, сохраняет его в PostgreSQL и возвращает
`202 Accepted`, ID и статус `created`. `GET /notifications/{id}` возвращает текущее
состояние. Публикация в RabbitMQ и переход в `queued` добавляются в задаче #6.

Оба метода требуют `X-API-Key` активного магазина. Ключ сверяется по SHA-256 с
`shops.api_key_hash`. Регистрация магазинов реализуется отдельно в задаче #8.
Чужое или отсутствующее уведомление возвращает `404`, неверный ключ — `401`.

При создании нужен `Idempotency-Key`: от 1 до 128 символов из `A-Z`, `a-z`, `0-9`,
`._:-`. Повтор с тем же ключом и сообщением возвращает `200` и текущее уведомление,
с другим сообщением — `409`. Ключи независимы для разных магазинов.

```bash
curl -i http://localhost:8000/notifications \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_STORE_KEY' \
  -H 'Idempotency-Key: order-123-sms' \
  -d '{"channel":"sms","recipient":"+79990000000","body":"Заказ принят"}'
```

Каналы и обязательные поля:

| Канал | Поля | Ограничения |
| --- | --- | --- |
| `email` | `channel`, `recipient`, `subject`, `body` | Email до 254 символов, тема до 200, текст до 10000 |
| `sms` | `channel`, `recipient`, `body` | Номер E.164, текст до 160 символов |
| `push` | `channel`, `recipient`, `title`, `body` | Токен до 320 символов, заголовок до 100, текст до 1000 |

Пустые и состоящие только из пробелов строки, строки с `U+0000`, лишние поля и некорректные значения
возвращают `422`. Исходные строки сохраняются без нормализации.
Push-заголовок хранится в `notifications.subject`, текст — в `notifications.content`.

`docs/openapi.yaml` в отдельной ветке остаётся ориентиром будущего API.
Текущая реализация использует целочисленные ID и статусы из моделей БД, без
префикса `/api/v1`, биллинга и истории попыток. Актуальные схемы доступны в `/docs`.

Интеграционные тесты создают отдельную случайную схему в PostgreSQL и удаляют её
после выполнения. Пользователь тестовой БД должен иметь право создавать схемы.
Без `TEST_DATABASE_URL` эти тесты пропускаются; в CI PostgreSQL запускается автоматически.

```bash
TEST_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/TEST_DB uv run pytest
```

## Настройки

Все настройки задаются переменными окружения, образец лежит в `.env.example`. Логины и пароли обязательны: без них приложение и `docker compose` не стартуют.

Новая настройка добавляется в `src/app/config.py` и `.env.example` в том же PR, где она понадобилась.

## Проверки качества кода

```bash
uv run ruff check .          # линтер
uv run ruff format .         # форматирование
uv run mypy                  # проверка типов
uv run pytest                # тесты
uv run pre-commit run --all-files   # все проверки сразу
```

Хуки pre-commit запускаются автоматически при `git commit`. Если ruff переформатировал файлы, сделайте `git add .` и повторите коммит.

## CI

На каждый PR GitHub Actions запускает ruff, mypy и pytest. PR с красным CI не мержим.

## Миграции

```bash
uv run alembic upgrade head                              #применить миграции
uv run alembic revision --autogenerate -m "description"     # создать миграцию по моделям
uv run alembic downgrade -1                              # откатить последнюю
```
