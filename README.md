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

`POST /notifications` принимает сообщение, сохраняет уведомление и outbox-задание
одной транзакцией PostgreSQL и возвращает `202 Accepted`, ID и статус `created`.
`GET /notifications/{id}` возвращает текущее состояние. При недоступности RabbitMQ
API продолжает принимать сообщения; задания остаются в outbox до публикации.

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

## Очереди и воркер

После запуска PostgreSQL и RabbitMQ примените миграции и запустите процессы
в отдельных терминалах из корня проекта:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run python -m app.messaging.relay
uv run python -m app.worker email
uv run python -m app.worker sms
uv run python -m app.worker push
```

Топология объявляется автоматически: durable direct exchange `notifications` и
три durable очереди `notifications.email`, `notifications.sms`, `notifications.push`.
Routing key соответствует каналу. Формат задания:

```json
{"notification_id": 123, "channel": "sms"}
```

Relay выбирает неопубликованное событие через `FOR UPDATE SKIP LOCKED`, переводит
уведомление из `created` в `queued` и отправляет persistent-сообщение с
`mandatory=True` и publisher confirms. После подтверждения коммитит статус и
`published_at`. При ошибке публикации транзакция откатывается; следующая попытка
выполняется через секунду. Пустой outbox также проверяется раз в секунду.
Можно запускать несколько relay: заблокированные события пропускаются.

Воркер получает по одному сообщению без автоматического ack. Переход из
`created`/`queued` в `sending` выполняется условным UPDATE, затем коммитится,
и только после этого отправляется ack. Переход из `created` допустим, если
публикация дошла до RabbitMQ, а коммит relay не подтвердился. Повторные задачи
для `sending`, `delivered`, `failed` подтверждаются без повторной обработки.
Повторная публикация outbox не откатывает `sending` обратно в `queued`.

Если БД недоступна, воркер ждёт секунду и возвращает задачу в очередь через nack.
Невалидный JSON и задания с неправильным каналом отклоняются без возврата в очередь.
Задания для отсутствующих уведомлений или несовпадающего канала в БД подтверждаются
без изменения данных. DLQ, отложенные бизнес-retry, провайдеры и восстановление
незавершённой отправки относятся к следующим задачам. Сейчас каркас завершает
обработку на статусе `sending` и не выполняет доставку.

Транспорт использует `aio-pika.connect_robust` для восстановления соединений.
При первоначальном запуске PostgreSQL и RabbitMQ должны быть доступны.
Потеря подтверждения или сбой до коммита допускают дубли сообщений; защита от них
находится в БД, гарантии exactly-once для внешней доставки пока нет.

RabbitMQ-тестам нужен отдельный тестовый брокер или vhost: они очищают три очереди
перед и после сценария. Не указывайте рабочий брокер в `TEST_RABBITMQ_URL`.
Без этой переменной тесты RabbitMQ пропускаются; в CI брокер поднимается автоматически.

```bash
TEST_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/TEST_DB \
TEST_RABBITMQ_URL=amqp://USER:PASSWORD@localhost:5672/TEST_VHOST \
uv run pytest
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
