# Operations Runbook — Madhavbaug Clinic Management System

Operational procedures for the single-VPS production deployment. The stack is
defined in `infra/docker-compose.yml` and fronted by Caddy (`infra/edge`).

## 1. Topology

| Service    | Image / build            | Purpose                                      |
| ---------- | ------------------------ | -------------------------------------------- |
| `edge`     | `infra/edge/Dockerfile`  | Caddy: TLS, security headers, SPA + `/api`   |
| `api`      | `apps/api/Dockerfile`    | FastAPI (uvicorn), runs migrations on start  |
| `worker`   | `apps/api/Dockerfile`    | Celery worker (dispatch, AI, non-response)   |
| `beat`     | `apps/api/Dockerfile`    | Celery Beat (periodic schedule)              |
| `postgres` | `postgres:16-alpine`     | Authoritative datastore                      |
| `redis`    | `redis:7-alpine`         | Celery broker (`/1`) + result backend (`/2`) |

Only ports **80/443** are published; Postgres and Redis stay on the private
compose network. Media lives on the `media_data` volume mounted at `/data/media`.

## 2. First-time deployment

1. **Provision** a VPS with Docker + Compose, point the clinic domain's DNS A
   record at the server, and open ports 80/443.
2. **Configure** the environment on the server:

   ```bash
   git clone <repo> && cd madhavbaug
   cp .env.example .env
   # edit .env (see section 3); generate secrets with: openssl rand -hex 32
   ```

3. **Bring the stack up** (builds API + edge images, applies migrations):

   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env up -d --build
   ```

4. **Seed** the bootstrap owner (idempotent) and confirm health:

   ```bash
   docker compose -f infra/docker-compose.yml exec api python -m app.cli seed
   curl -fsS https://<domain>/health/ready
   ```

## 3. Production environment (safety gate)

`APP_ENV=production` activates a hard startup gate. The API/worker **refuse to
boot** unless every item below is satisfied (PRD AC-012 / Risk 8):

| Variable                     | Requirement                                              |
| ---------------------------- | -------------------------------------------------------- |
| `APP_DEBUG`                  | `false`                                                   |
| `SECRET_KEY`                 | unique, ≥ 32 chars, not the development default           |
| `MEDIA_SIGNING_SECRET`       | unique, not the development default                       |
| `BOOTSTRAP_ADMIN_PASSWORD`   | changed from the placeholder                              |
| `WHATSAPP_VERIFY_TOKEN`      | changed from the placeholder                              |
| `WHATSAPP_APP_SECRET`        | required when `WHATSAPP_ENABLED=true`                     |
| `OPENAI_API_KEY`             | required when `AI_ENABLED=true`                           |
| `BACKEND_CORS_ORIGINS`       | real origin(s); must not contain `localhost`/`127.0.0.1`  |

Keep `WHATSAPP_ENABLED=false` and `AI_ENABLED=false` until the clinic has
approved live patient messaging / AI data handling (see Open Questions 12, 14).

## 4. Standard redeploy

```bash
git pull
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
```

`api` runs `alembic upgrade head` on start (`MIGRATE_ON_START=true`); workers and
beat intentionally do **not**, to avoid concurrent migrations. Verify:

```bash
docker compose -f infra/docker-compose.yml ps
curl -fsS https://<domain>/health/ready
```

## 5. Backups and restore

**Postgres** (nightly cron on the host):

```bash
docker compose -f infra/docker-compose.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > /backups/mb-$(date +%F).sql.gz
```

**Media** volume (nightly):

```bash
docker run --rm -v madhavbaug_media_data:/data -v /backups:/b alpine \
  tar czf /b/media-$(date +%F).tar.gz -C /data .
```

Retain at least 30 daily + 12 monthly copies off the VPS. **Test restores**
quarterly:

```bash
gunzip -c /backups/mb-YYYY-MM-DD.sql.gz | \
  docker compose -f infra/docker-compose.yml exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Redis is a broker/cache and is **not** backed up; in-flight tasks are re-created
by Beat within one schedule interval.

## 6. Migrations

- Applied automatically by the `api` service on start.
- To apply manually: `docker compose exec api alembic upgrade head`.
- Inspect current revision: `... exec api alembic current`.
- **Downgrades** are intentionally manual: `alembic downgrade -1`. Some
  migrations drop enums manually by design; review the revision before running.
- Never run migrations against a database being restored at the same time.

## 6.1 Secrets rotation

Rotating `SECRET_KEY` invalidates all issued JWTs (staff re-login). To rotate:

1. Update `.env`.
2. `docker compose ... up -d api worker beat` (recreates containers).
3. Confirm login + readiness.

Rotate `MEDIA_SIGNING_SECRET` the same way (previously issued signed URLs
expire within `MEDIA_URL_TTL_SECONDS`). Rotate the WhatsApp `APP_SECRET` only
together with the Meta app dashboard setting, or webhooks will be rejected.

## 6. Monitoring

- **Liveness:** `GET /health` — process is up.
- **Readiness:** `GET /health/ready` — checks Postgres + Redis; returns HTTP
  **503** with `status: degraded` if a dependency is down (200 otherwise).
- **Logs:** structured JSON in production (`docker compose logs -f api worker`).
  Every request/response carries `X-Request-ID` for correlation.
- **Queues/visibility:** the dashboard exposes follow-up, alert, clarification
  and failed-delivery counts; the Analytics page consolidates daily actions.
- **Watch for:** `delivery_failure` alerts, growing `message_exceptions`, Celery
  result failures, and readiness `degraded`.

## 7. Incident runbooks

### 7.1 Inbound webhook backlog / duplicates
Symptoms: provider retries, many `duplicate` results. This is **safe**: webhook
bodies are deduplicated by hash and inbound messages by provider id. Confirm
`POST /api/v1/whatsapp/webhook` returns 200 and check `message_exceptions`.

### 7.2 Stuck or failed outbound messages
1. Check `delivery_failure` alerts and the Messages tab.
2. Verify `WHATSAPP_ENABLED`, token and phone-number id.
3. Re-run dispatch: `POST /api/v1/messages/dispatch` (or wait for Beat).
Failed instances are marked `failed` and surfaced as alerts; they are never
silently retried indefinitely.

### 7.2 Non-response / escalation
Beat runs `process-non-response` every 5 minutes. If reminders/escalations stop:
verify `beat` is running, check workers executed the task, and inspect
`docker compose logs worker | grep process_non_response`.

### 7.3 AI provider outage
The AI layer degrades **safely**: with `ai_enabled=false` (or no key) a
deterministic heuristic extractor runs; a provider error is recorded as a
`failed` extraction with **no** observations created. Thresholds are always
evaluated by the deterministic rule engine, never the model. No action needed
beyond monitoring; re-run failed extractions with the staff "reanalyze" action.

### 7.2 WhatsApp / Meta outage
Outbound sends fail → instances marked `FAILED` with `delivery_failure` alerts;
non-response logic never treats a failed delivery as patient non-response.
Resume dispatch once Meta recovers (`POST /messages/dispatch`). A cluster of
`template_required` failures means a follow-up outside the 24-hour session window
has no approved, active template — attach one or bring the patient's replies
back inside the window (`WHATSAPP_SESSION_WINDOW_HOURS`).

Inbound media is downloaded to the `media_data` volume by a Celery worker and
served only through short-lived signed URLs (`/api/v1/media/{id}`, TTL
`MEDIA_URL_TTL_SECONDS`); if downloads fail, check the worker logs and that
`MEDIA_SIGNING_SECRET` is set.

### 7.3 Postgres down / readiness degraded
Bring Postgres back; `api` uses `pool_pre_ping` so stale connections recover.
The API stays readable only if the DB is reachable — restore from backup if the
volume is lost, then redeploy.

### 7.4 Disk full / media growth
Check `docker system df` and the `media_data` volume. Media retention should be
agreed with the clinic (Open Question 16). Prune dangling images/logs:
`docker system prune -f`. Log files are capped (10 MB × 5 per container).

### 7.5 Rollback
Redeploy the previous image tag / commit (`git checkout <sha> && up -d --build`).
If a migration must be reverted, use Alembic downgrade **only** after a verified
backup; prefer a forward fix.

## 8. Scaling notes

The single-VPS stack comfortably handles the clinic's early load. When needed:
scale Celery `worker` replicas horizontally (`--scale worker=3`); keep a single
`beat`. Celery tasks are idempotent (deduped alerts, unique schedule+date
instances, provider-id message dedupe), so horizontal workers are safe. Move
media to object storage before scaling `api` beyond one host, since media is
currently a local volume.

## 9. Security checklist (production)

- [ ] Production safety gate passes (section 3) — API boots with `APP_ENV=production`.
- [ ] TLS issued by Caddy for the real domain; HSTS enabled.
- [ ] `WHATSAPP_APP_SECRET` set and `WEBHOOK_ALLOW_UNSIGNED` unset so unsigned
      webhooks are rejected with 403 (production always enforces signatures).
- [ ] `WHATSAPP_ENFORCE_SESSION_WINDOW=true` when `WHATSAPP_ENABLED=true` so
      business-initiated messages outside the 24h window use approved templates.
- [ ] Debug off; no dev CORS origins; secrets unique and stored outside git.
- [ ] Backups scheduled and a restore has been rehearsed.
- [ ] Only 80/443 reachable from the internet.
