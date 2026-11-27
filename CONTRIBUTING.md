# Как работать с проектом

## Правила

- Один PR решает одну задачу и содержит свои тесты.
- Ветки называем по типу: `feat/...`, `fix/...`, `chore/...`, `docs/...`.
- В `main` напрямую не пушим, мерж через PR минимум с одним апрувом.
- Сообщения коммитов в формате `тип: описание` (`feat`, `fix`, `chore`, `test`, `docs`).
- Новая настройка добавляется в `src/app/config.py` и `.env.example` в том же PR.

## Проверки

```bash
uv run ruff check .
uv run ruff format .
uv run mypy
uv run pytest
uv run pre-commit run --all-files
```

Хуки pre-commit запускаются при `git commit`. Если ruff переформатировал файлы, сделайте `git add .` и повторите коммит.

## CI

На каждый PR GitHub Actions запускает ruff, mypy и pytest. PR с красным CI не мержим.