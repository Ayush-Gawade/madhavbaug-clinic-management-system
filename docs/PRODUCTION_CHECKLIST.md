# Production Deployment Checklist — Madhavbaug Clinic Management System

Pre-deployment checklist for the single-VPS production stack defined in
`infra/docker-compose.yml` and fronted by Caddy (`infra/edge`). Operational
procedures live in [`docs/RUNBOOK.md`](RUNBOOK.md); this checklist is the
pre-flight list that must pass before a production deploy is executed.

> **Security:** never read, print, copy or commit real secrets. `.env`,
> `env.env`, `env.*.env`, `*.pem` and `*.key` are git-ignored. This document
> references environment variable **names only** — values are never recorded
> here. See [`docs/PRODUCTION_ENV_VARS.md`](PRODUCTION_ENV_VARS.md).

## 1. Code / branch readiness

- [ ] Release branch is `deploy/oracle-production` (currently at commit
      `0fdb878`, identical to the `master` tip on origin).
- [ ] All production hardening changes (WhatsApp fail-closed behaviour, prod
      docs shutdown, HTTPS/public-URL gate, dedicated outbound timeout, safety
      tests) are **committed** on the release branch and pushed to origin.
      *(Not completed in the inspection session — requires owner approval.)*
- [ ] Working tree contains no leftover local-only changes that belong to the
      release (see `git status`).
- [ ] `apps/api` quality gates green locally:
      `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`
- [ ] Web quality gates green locally:
      `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
- [ ] CI workflow (`.github/workflows/ci.yml`) green for the release commit
      (API + Web + Infra jobs). Status for the current tip was reported as
      `pending` with no recorded check runs at inspection time.

## 2. Production safety gate (`APP_ENV=production`)

The API and worker **refuse to boot** when any of the following fails
(`apps/api/app/core/config.py`, PRD AC-012 / Risk 8):

- [ ] `APP_ENV=production`
- [ ] `APP_DEBUG=false`
- [ ] `SECRET_KEY` — unique, ≥ 32 chars, not the development default
- [ ] `MEDIA_SIGNING_SECRET` — unique, not the development default
- [ ] `BOOTSTRAP_ADMIN_PASSWORD` — changed from the placeholder
- [ ] `WHATSAPP_VERIFY_TOKEN` — changed from the placeholder
- [ ] `WHATSAPP_APP_SECRET` — set (required in production even when
      `WHATSAPP_ENABLED=false`)
- [ ] `WHATSAPP_ENABLED=false` for the initial go-live, **or** all of:
      - `WHATSAPP_ACCESS_TOKEN` set
      - `WHATSAPP_PHONE_NUMBER_ID` set
      - `WHATSAPP_ENFORCE_SESSION_WINDOW=true`
      - `WHATSAPP_SESSION_WINDOW_HOURS=24` (approved template configured in
        Meta for out-of-window business sends)
- [ ] `WHATSAPP_WEBHOOK_REQUIRE_SIGNATURE=true` and
      `WEBHOOK_ALLOW_UNSIGNED=false`
- [ ] `AI_ENABLED=false` for the initial go-live, **or** (when enabled):
      - `OPENAI_API_KEY` set
      - `AI_PROCESSING_MODE=deferred`
- [ ] `PUBLIC_BASE_URL=https://<real-public-hostname>` (no `localhost`/`127.0.0.1`)
- [ ] `BACKEND_CORS_ORIGINS=<real-origin>[, …]` (no `localhost`/`127.0.0.1`)
- [ ] `/docs`, `/redoc`, `/openapi.json` return `404` with the release build

## 3. Secrets & configuration on the VM

- [ ] `.env` created on the server from `.env.example` and filled with real
      values (never committed; never pasted into chat/logs).
- [ ] `docker compose -f infra/docker-compose.yml config` validates cleanly.
- [ ] Postgres credentials in use are the ones matching the **existing**
      production database volume (do not silently re-init the volume).
- [ ] `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` set for the clinic
      owner (seed is idempotent).

## 4. Infrastructure readiness (Oracle Cloud Ubuntu 22.04 VM)

- [ ] Docker Engine + Compose plugin installed on the VM.
- [ ] Oracle Cloud security list / firewall allows inbound TCP `80` and `443`.
- [ ] DNS: clinic hostname `A` record points to the VM public IP
      (`137.23.63.69`) and is reachable.
- [ ] Ports `5432`/`6379` NOT published on host (compose default: internal only).

## 5. Backup before first production deploy

- [ ] `pg_dump` snapshot of the existing production database taken.
- [ ] Media volume snapshot (`media_data`) taken.
- [ ] Restore of a backup rehearsed on a scratch volume (quarterly practice).

## 6. Deployment

- [ ] Run preflight: `./infra/scripts/preflight.sh` (or documented compose checks).
- [ ] Deploy: `docker compose -f infra/docker-compose.yml --env-file .env up -d --build`.
- [ ] Migrations applied via `MIGRATE_ON_START=true` (api container) or manual
      `alembic upgrade head`.
- [ ] Worker + beat started; beat schedules intact.

## 7. Post-deploy verification

- [ ] `docker compose -f infra/docker-compose.yml ps` — all services running.
- [ ] `GET /health` → `200 {"status":"ok"}`.
- [ ] `GET /health/ready` → `200` with `components.database=ok`,
      `components.redis=ok` (or `503 degraded` while a dependency is down).
- [ ] Public URL serves the SPA and proxies `/api/v1` → API (Caddy).
- [ ] `GET /docs`, `/redoc`, `/openapi.json` → `404` in production.
- [ ] Bootstrap admin can log in (JWT flow) and reach the dashboard.
- [ ] WhatsApp disabled / AI disabled (or live credentials validated) before
      enabling patient-facing messaging.

## 8. Rollback

- [ ] Previous image tag / commit available.
- [ ] DB backup verified (see section 5).
- [ ] `docker compose ... up -d --build <previous-ref>`; prefer forward fix
      over downgrades; migrations downgrades manual only.

## 9. Approval-gated actions (require explicit user approval)

The following actions must be explicitly approved by the operator before being
executed by an agent:

1. Committing and pushing the release branch / any code changes.
2. Writing real secret values to the server `.env`.
3. Running the production deploy (`docker compose up -d --build`).
4. Any destructive operation (volume removal, DB restore over live data,
   rollback with downgrade).
5. Enabling `WHATSAPP_ENABLED=true` / `AI_ENABLED=true` with live credentials.
6. Any change to backups/retention schedule.
