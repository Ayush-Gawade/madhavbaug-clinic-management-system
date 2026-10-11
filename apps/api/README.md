# Madhavbaug API

FastAPI backend, Celery workers and scheduler for the Madhavbaug Clinic
Management System. See the repository root `README.md` for full setup, and
`docs/ROADMAP.md` for build status.

## Layout

```
app/
  api/v1/        HTTP routers (versioned)
  core/          config, security, logging, errors, middleware, redis
  db/            declarative base, mixins, async session
  models/        SQLAlchemy ORM models
  schemas/       Pydantic request/response schemas
  services/      domain services
  workers/       Celery app and tasks
  main.py        application factory
  cli.py         admin commands (python -m app.cli seed)
alembic/         migrations
tests/           unit + integration tests
```

## Common commands

```bash
uv sync                       # install dependencies
uv run alembic upgrade head   # apply migrations
uv run python -m app.cli seed # create bootstrap admin
uv run uvicorn app.main:app --reload
uv run celery -A app.workers.celery_app.celery_app worker -l info
uv run celery -A app.workers.celery_app.celery_app beat -l info
```

## Quality gates

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest
```
