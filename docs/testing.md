# Тесты

```bash
uv run pytest
```

Юнит-тесты запускаются без внешних сервисов. Интеграционным тестам нужны отдельные тестовые PostgreSQL и RabbitMQ. Без соответствующих переменных они пропускаются. В CI PostgreSQL и RabbitMQ поднимаются автоматически.

## PostgreSQL

Переменная `TEST_DATABASE_URL`. Тесты создают отдельную случайную схему и удаляют её после выполнения, поэтому пользователь тестовой БД должен иметь право создавать схемы.

## RabbitMQ

Переменная `TEST_RABBITMQ_URL`. Нужен отдельный тестовый брокер или vhost: тесты очищают три очереди до и после сценария. **Не указывайте рабочий брокер.**

## Полный запуск

```bash
TEST_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/TEST_DB \
TEST_RABBITMQ_URL=amqp://USER:PASSWORD@localhost:5672/TEST_VHOST \
uv run pytest
```