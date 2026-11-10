# Production Environment Variable Inventory — Madhavbaug

Environment variable **names only**. Never commit or print real values.

## Application

| Variable              | Required in production | Notes |
| --------------------- | ---------------------- | ----- |
| `APP_NAME`            | no                     | Display name. |
| `APP_ENV`             | yes                    | Must be `production`. |
| `APP_DEBUG`           | yes                    | Must be `false`. |
| `APP_TIMEZONE`        | no                     | Default `Asia/Kolkata`. |
| `API_V1_PREFIX`       | no                     | Default `/api/v1`. |
| `BACKEND_CORS_ORIGINS`| yes                    | Real origin(s); no localhost. |
| `PUBLIC_BASE_URL`     | yes                    | `https://<real-host>`; no localhost. |
| `PUBLIC_HOST`         | yes                    | Hostname Caddy serves; no scheme. |

## Web build-time (injected when building the SPA image)

| Variable           | Required in production | Notes |
| ------------------ | ---------------------- | ----- |
| `VITE_API_BASE_URL`| no                    | Default `/api/v1` (same-origin behind Caddy). |

## Security / auth

| Variable                        | Required in production | Notes |
| ------------------------------- | ---------------------- | ----- |
| `SECRET_KEY`                    | yes                    | Unique, ≥ 32 chars. |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | no                     | Default 30. |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | no                     | Default 20160 (14 days). |
| `JWT_ALGORITHM`                 | no                     | Default `HS256`. |
| `BOOTSTRAP_ADMIN_EMAIL`        | yes                    | Bootstrap owner email. |
| `BOOTSTRAP_ADMIN_PASSWORD`     | yes                    | Changed from placeholder. |

## Database

| Variable              | Required in production | Notes |
| --------------------- | ---------------------- | ----- |
| `POSTGRES_HOST`       | yes (compose override) | `postgres` in compose network. |
| `POSTGRES_PORT`       | yes (compose override) | `5432`. |
| `POSTGRES_USER`       | yes                    | From `.env`; must match existing DB. |
| `POSTGRES_PASSWORD`   | yes                    | From `.env`. |
| `POSTGRES_DB`         | yes                    | From `.env`. |
| `DATABASE_URL`        | yes (compose override) | Full async URI; wins over POSTGRES_\*. |
| `TEST_DATABASE_URL`   | no                     | Integration tests only. |

## Redis / Celery

| Variable                 | Required in production | Notes |
| ------------------------ | ---------------------- | ----- |
| `REDIS_HOST`             | yes (compose override) | `redis`. |
| `REDIS_PORT`             | yes (compose override) | `6379`. |
| `REDIS_DB`               | no                     | Default 0. |
| `CELERY_BROKER_URL`     | yes (compose override) | `redis://redis:6379/1`. |
| `CELERY_RESULT_BACKEND` | yes (compose override) | `redis://redis:6379/2`. |
| `CELERY_TASK_ALWAYS_EAGER` | no                 | Must stay `false` in production. |
| `LOCAL_SCHEDULER_ENABLED`| no                    | Ignored in production. |
| `LOCAL_SCHEDULER_INTERVAL_SECONDS` | no          | Default 30. |

## Media

| Variable                 | Required in production | Notes |
| ------------------------ | ---------------------- | ----- |
| `MEDIA_ROOT`             | yes (compose override) | `/data/media` (named volume). |
| `MEDIA_SIGNING_SECRET`  | yes                    | Unique, not the development default. |
| `MEDIA_URL_TTL_SECONDS` | no                     | Default 300. |

## OpenAI / AI

| Variable                | Required in production | Notes |
| ----------------------- | ---------------------- | ----- |
| `OPENAI_API_KEY`        | only if `AI_ENABLED`  | Required then; must be real. |
| `OPENAI_BASE_URL`       | no                     | Optional gateway. |
| `OPENAI_TEXT_MODEL`     | no                     | Default `gpt-4o`. |
| `OPENAI_VISION_MODEL`   | no                     | Default `gpt-4o`. |
| `OPENAI_TIMEOUT_SECONDS`| no                    | Default 45. |
| `OPENAI_MAX_RETRIES`    | no                     | Default 2. |
| `AI_ENABLED`            | yes                    | Keep `false` until clinic approval. |
| `AI_PROCESSING_MODE`   | yes                    | Must be `deferred` when AI enabled in production. |

## WhatsApp / Meta Cloud API

| Variable                          | Required in production | Notes |
| --------------------------------- | ---------------------- | ----- |
| `WHATSAPP_ENABLED`                | yes                    | Keep `false` until go-live approval. |
| `WHATSAPP_VERIFY_TOKEN`          | yes                    | Changed from placeholder. |
| `WHATSAPP_ACCESS_TOKEN`          | when enabled           | Required when `WHATSAPP_ENABLED=true`. |
| `WHATSAPP_PHONE_NUMBER_ID`       | when enabled           | Required when `WHATSAPP_ENABLED=true`. |
| `WHATSAPP_BUSINESS_ACCOUNT_ID`   | no                     | Meta account identifier. |
| `WHATSAPP_APP_SECRET`            | yes                    | Required in production even when disabled. |
| `WHATSAPP_TIMEOUT_SECONDS`       | no                     | Default 30. |
| `WHATSAPP_WEBHOOK_REQUIRE_SIGNATURE` | yes               | Must be `true`. |
| `WEBHOOK_ALLOW_UNSIGNED`        | no                     | Must be `false` in production. |
| `WHATSAPP_API_VERSION`           | no                     | Default `v21.0`. |
| `WHATSAPP_GRAPH_BASE_URL`       | no                     | Default `https://graph.facebook.com`. |
| `WHATSAPP_SESSION_WINDOW_HOURS` | no                     | Default 24. |
| `WHATSAPP_ENFORCE_SESSION_WINDOW` | yes (when enabled)  | Must be `true` in production when enabled. |

## Not application secrets (compose-managed)

| Variable        | Purpose |
| --------------- | ------- |
| `POSTGRES_HOST`/`POSTGRES_PORT` | Inside compose network (`postgres:5432`). |
| `REDIS_HOST`/`REDIS_PORT`       | Inside compose network (`redis:6379`). |
| `DATABASE_URL`    | Full override used by api/worker/beat. |
| `CELERY_BROKER_URL` | `redis://redis:6379/1`. |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2`. |
| `MEDIA_ROOT`      | `/data/media`. |
