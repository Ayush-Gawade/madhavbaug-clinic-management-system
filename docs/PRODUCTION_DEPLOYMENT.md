# Production Deployment Plan — Madhavbaug Clinic Management System

Safe, phased deployment plan for the existing Oracle Cloud Ubuntu 22.04
production VM (`137.23.63.69`, SSH user `ubuntu`) running branch
`deploy/oracle-production`.

Companion documents: [`docs/RUNBOOK.md`](RUNBOOK.md) (operations),
[`docs/PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md) (pre-flight list).

## Phase 0 — Approval gates (do not skip)

The following require explicit operator approval before anything below is
executed:

1. Commit + push the release branch / any code changes.
2. Write real secret values to the server `.env`.
3. Run the production deploy (`docker compose up -d --build`).
4. Destructive operations (volume removal, restore over live data, downgrade).
5. Enabling live WhatsApp / AI integrations.

## Phase 1 — Pre-deploy (on the VM)

```bash
git fetch origin
git checkout deploy/oracle-production   # or the approved release ref
docker compose -f infra/docker-compose.yml --env-file .env config --services
docker compose -f infra/docker-compose.yml --env-file .env ps
```

Backup (before first production deploy and before every redeploy where a
migration might run):

```bash
docker compose -f infra/docker-compose.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > /backups/mb-$(date +%F).sql.gz

docker run --rm -v madhavbaug_media_data:/data -v /backups:/b \
  alpine tar czf /b/media-$(date +%F).tar.gz -C /data .
```

## Phase 2 — Deploy

Preferred helper (build + start stack):

```bash
./infra/scripts/deploy.sh --build     # runs: docker compose -f infra/docker-compose.yml --env-file .env up -d --build
```

Or manually:

```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.yml ps
```

Notes:

- The `api` service entrypoint applies Alembic migrations
  (`MIGRATE_ON_START=true`); worker/beat do not.
- Named volumes (`postgres_data`, `redis_data`, `media_data`, `caddy_data`,
  `caddy_config`) are preserved — redeploy never deletes data.
- `WHATSAPP_ENABLED=false` and `AI_ENABLED=false` until the clinic approves live
  messaging / AI handling.

## Phase 3 — Post-deploy verification

```bash
curl -fsS http://localhost/health
curl -fsS http://localhost/health/ready
curl -fsS -o /dev/null -w '%{http_code}\n' https://<public-host>/docs   # expect 404
docker compose -f infra/docker-compose.yml logs -f api worker
docker compose -f infra/docker-compose.yml exec api python -m app.cli seed
```

## Phase 4 — Rollback

```bash
docker compose -f infra/docker-compose.yml up -d --build <previous-ref>
```

Prefer forward fixes; Alembic downgrades manual and only after verified backup.

## Phase 5 — Go-live enablement (post-deploy, approval-gated)

Order: WhatsApp credentials (`WHATSAPP_ENABLED=true`, token, phone number id,
app secret, session window enforcement) → AI (`AI_ENABLED=true`, key,
`AI_PROCESSING_MODE=deferred`) → dispatch verification via
`POST /api/v1/messages/dispatch`.

## Automation status

| Step | Can agent execute now? | Requires approval |
| ---- | ------------------------ | ----------------- |
| Read-only preflight checks | yes (local + VM) | no |
| Commit / push release | no | **yes** |
| Write server `.env` values | no | **yes** |
| Deploy (compose up) | no | **yes** |
| Backup execution | no | **yes** |
| Post-deploy verification commands | yes (dry-run/read-only) | no |
| Enable live WhatsApp / AI | no | **yes** |
