# Madhavbaug — Clinic Management System

A production-oriented clinic management platform with WhatsApp-based patient
engagement, AI-assisted monitoring, rule-based clinical alerts, and
treatment-level profitability analysis.

> Source of truth is the **PRD** (`docs/`). This repository implements it in
> increments. See `docs/ROADMAP.md` for status.

## Architecture

| Layer    | Technology                                                          |
| -------- | ------------------------------------------------------------------- |
| Frontend | React 18 + Vite + TypeScript                                        |
| Backend  | FastAPI + SQLAlchemy 2.0 (async) + Alembic + Pydantic v2             |
| Database | PostgreSQL 16                                                       |
| Jobs     | Celery + Redis (broker/results) + Celery Beat (scheduler)           |
| AI       | OpenAI gpt-4o (text) + gpt-4o vision (meal images), structured JSON |
| Messaging| Meta WhatsApp Cloud API                                            |
| Media    | Inbound media referenced by provider id (storage + signed URLs not yet implemented) |
| Infra    | Docker Compose (dev + single-VPS prod), Caddy reverse proxy         |

## Repository layout

```
apps/api   FastAPI backend, Celery workers, Alembic migrations, tests
apps/web   React + Vite + TypeScript staff dashboard
infra      Docker Compose, reverse proxy config, env templates
docs       Runbooks, ADRs, roadmap, Meta/WhatsApp setup checklist
```

## Quick start (development)

### 1. Configure environment

```bash
cp .env.example .env
# edit .env and set SECRET_KEY, MEDIA_SIGNING_SECRET, OPENAI_API_KEY, etc.
```

### 2. Start infrastructure (Postgres + Redis)

```bash
docker compose -f infra/docker-compose.dev.yml up -d postgres redis
```

### 3. Backend

```bash
cd apps/api
uv sync
uv run alembic upgrade head
uv run python -m app.cli seed          # bootstrap admin + demo settings
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

### 4. Worker + scheduler (separate terminals)

```bash
cd apps/api
uv run celery -A app.workers.celery_app worker -l info
uv run celery -A app.workers.celery_app beat -l info
```

### 5. Frontend

```bash
cd apps/web
pnpm install
pnpm dev
```

Dashboard: http://localhost:5173

## Testing and quality gates

```bash
cd apps/api && uv run pytest          # backend tests
cd apps/api && uv run ruff check .    # lint
cd apps/api && uv run mypy app        # types
cd apps/web && pnpm lint && pnpm typecheck && pnpm test
```

## Core invariants (enforced in code and tests)

- Clinical history is **append-only**; new readings never overwrite old ones.
- Numeric safety thresholds are evaluated by a **deterministic rule engine**,
  never by an LLM.
- WhatsApp is an interface only; the **database is authoritative**.
- AI output never silently changes a care plan or makes a clinical decision.
- Failed delivery and patient non-response are always distinct states.
- Missing data is never treated as compliance or as evidence of wellness.

uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 7. Production deployment

The full single-VPS stack (Caddy edge + API + worker + beat + Postgres + Redis)
and all operational procedures live in **`docs/RUNBOOK.md`**:

```bash
cp .env.example .env   # set real secrets and APP_ENV=production
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.yml exec api python -m app.cli seed
```

Production startup is gated: the API/worker refuse to boot with placeholder
secrets, `APP_DEBUG=true`, missing webhook/AI secrets, or localhost CORS
origins (PRD AC-012, `app/core/config.py`).

## License


Proprietary — for the Madhavbaug clinic engagement.
