# Roadmap

Status of the incremental build of the Madhavbaug Clinic Management System.
Each increment is independently demoable and verified before the next begins.

| # | Increment | Status |
| - | --------- | ------ |
| 1 | Foundation: monorepo, Docker Compose, FastAPI core, auth + RBAC, Vite shell, CI | ✅ done |
| 2 | Patients, categories, consent, observations, care plans, timeline | ✅ done (API) |
| 3 | Dashboard + patient detail UI | ✅ done |
| 4 | Financial module (costs, payments, estimator, discount boundary) | ✅ done |
| 5 | Scheduling core (schedules, instances, Celery Beat, templates) | ✅ done |
| 6 | WhatsApp inbound/outbound (webhook, idempotency, media, exception queue) | ✅ done |
| 7 | Rule engine + alerts + review/escalation queues | ✅ done |
| 8 | AI text + vision, provenance, clarification, human review | ✅ done |
| 9 | Non-response / reminder / escalation end-to-end | ✅ done |
| 10 | Analytics & reporting (overview, operations, adherence, trends, finance) | ✅ done |
| 11 | Hardening, safety/failure test matrix, prod deploy, runbooks | ✅ done |

## Increment 1 deliverable

- Monorepo layout (`apps/api`, `apps/web`, `infra`, `docs`, CI).
- Docker Compose for dev infra (Postgres + Redis) and a full single-VPS stack
  (api, worker, beat, edge/Caddy).
- FastAPI app factory: structured logging, request-id middleware, consistent
  error envelope, CORS, liveness/readiness probes.
- Async SQLAlchemy 2.0 + Alembic (async) + settings via pydantic-settings.
- Auth: Argon2 password hashing, JWT access/refresh with rotation + revocation,
  staff RBAC (owner/doctor/dietitian/reception/finance), bootstrap-admin CLI.
- Append-only audit-event foundation.
- React + Vite + TS SPA shell: login, auth context, protected routes, layout.
- Quality gates: ruff, mypy (strict), pytest (unit + integration), eslint,
  tsc, vitest, GitHub Actions.

## Increment 2 deliverable (API)

- Clinical models + migration: `patients`, `patient_categories`,
  `consent_records`, `observations` (append-only, units + source + context),
  `care_plans` (versioned; activating a new plan archives the previous one).
- RBAC: patient/clinical endpoints for owner, reception, doctor, dietitian;
  finance excluded. Enum-typed query filters with 422 on invalid values.
- Endpoints: patient register/list/search/filter/update, category assign/list
  (409 on duplicate active), consent add/list/withdraw, observation add/list
  (timezone-aware, newest first), care-plan create/list, patient timeline
  (aggregates all event types, newest first).
- Safe-posting of ORM results after server-side `onupdate` (async refresh);
  JSON-safe pydantic validation error rendering.
- 8 new integration tests covering the full clinical lifecycle (23 total).

## Increment 3 deliverable (UI)

- Shared UI primitives (Button, Input, Select, Badge, Card, Modal, empty/error
  states) and `src/lib/patients.ts` typed API client; `src/lib/format.ts`.
- Patients page: search (name/ID/phone), category + status filters, real
  pagination, register-patient modal with language + categories.
- Patient detail: tabs for Overview (record + category assignment), Observations
  (record + newest-first table), Care plan (versioned create/list), Timeline
  (aggregated activity feed), Consents (record list).
- Dashboard: live active/registered patient counts + backend status card.
- Gates: lint, tsc, vitest, production build all green.

## Increment 4 deliverable

- Finance models + migration: `treatments` (catalog: list price, royalty %,
  therapist/material/other-overhead costs, active flag), `patient_treatment_assignments`
  (status, discount %, period, assigned-by, eager `treatment` relation),
  `payments` (payment/refund, method, reference, optional treatment tie).
- Estimator: percent-safe `Decimal` math (`ROUND_HALF_UP`), boundary derivation
  (`r_min`, max allowable discount), cost-accounting `canonicalize_discount`.
- RBAC: treatment catalog CRUD + estimator for owner/finance; assignment/payment/
  summary for owner/finance/reception; treatment read for clinical staff + finance.
  Discounts > 50% (default boundary) require owner, enforced server-side via audit.
- Endpoints: treatments CRUD (409 on duplicate code), estimator, patient
  assignment (409 on duplicate active / inactive treatment), payments
  (payment/refund), per-patient finance summary (charges − paid = outstanding).
- Config-driven boundaries: `finance_min_contribution_margin`, `finance_min_profit`,
  `finance_max_discount_default`.
- Expandable web UI: Finance page (catalog + live estimator slider with
  boundary warnings) and a Finance tab on patient detail (summary cards,
  assign treatment, record payment, charges/payment lists).
- 6 new finance integration tests (28 total); live E2E smoke verified
  (charge = list × discount, outstanding math correct, high-discount flagged).

## Increment 5 deliverable

- Scheduling models + migration: `follow_up_schedules` (recurrence rule,
  timezone, local time, response deadline, reminder/escalation policy, active
  range, responsible staff), `follow_up_instances` (one occurrence; unique on
  schedule + due date), `message_templates` (approved content).
- Deterministic recurrence engine (daily/weekly/monthly) with validation and
  clamped month-ends; no external scheduler dependency.
- Services: schedule CRUD, idempotent materialization (look-ahead window),
  eligibility-checked dispatch (schedule state, active range, communication
  consent), operations queue with filters/pagination, dashboard day counts,
  template CRUD.
- Endpoints: `/schedules` (create/list/get/patch), `/schedules/{id}/materialize`,
  `/schedules/process-due`, `/instances` queue, `/follow-ups/day-count`,
  `/messages/templates` CRUD. RBAC: finance excluded from scheduling.
- Celery Beat wiring: `materialize-follow-ups` (every 10 min) and
  `process-due-follow-ups` (every 2 min) tasks over a fresh async session.
- Web: Follow-ups operations page (status queue, pagination, run-dispatch
  action, due/overdue/done counters) and live dashboard follow-up counts.
- 6 new scheduling integration tests (34 total); live E2E smoke verified
  (daily schedule to 8 instances, idempotent re-run, consent-gated dispatch,
  queue + day counts).

## Increment 6 deliverable

- Messaging models + migration: `whatsapp_messages` (direction, provider id,
  type, text/media, delivery + processing status, instance/patient links),
  `message_delivery_events` (append-only status transitions),
  `webhook_events` (deduplicated by body hash; signature flag), `message_exceptions`
  (open/resolved/dismissed with reason + resolver).
- WhatsApp client (`services/whatsapp.py`): `X-Hub-Signature-256` HMAC
  verification, subscription-challenge verification, webhook normalization
  (messages + statuses), text/template sends over the Graph API, media download,
  and `{{placeholder}}` template rendering. Dry-run mode when the integration is
  disabled so the full flow works without live credentials.
- Services: outbound dispatch (QUEUED instances → sent/tracked message + delivery
  event → instance SENT/FAILED), idempotent inbound handling (dedupe by provider
  event/message id), tolerant phone-to-patient matching, latest-open-instance
  association (instance → RESPONDED), delivery-status application, conversation
  listing and a staff exception queue with resolve/dismiss.
- Endpoints: public `GET/POST /whatsapp/webhook` (handshake + HMAC verification),
  `POST /messages/dispatch`, `GET /patients/{id}/messages`,
  `GET /messages/exceptions`, `POST /messages/exceptions/{id}/resolve`.
  RBAC: clinical/reception roles only; finance excluded.
- Celery Beat `dispatch-outbound-messages` (every minute) over a fresh session.
- Web: read-only "Messages" conversation tab on patient detail (inbound/outbound
  bubbles, media/type, delivery badges).
- 13 new tests (47 total: 6 client unit + 7 messaging integration); ruff, format,
  mypy (strict), eslint, tsc, vitest and production build all green.

## Increment 7 deliverable

- Alert models + migration: `safety_rules` (versioned by `rule_key`; new threshold =
  new `version` row with prior active row deactivated), `alerts` (patient,
  observation/instance/rule links, metric/value/unit, type, priority, status,
  review metadata), `clinician_actions` (append-only disposition history).
- Deterministic rule engine (`services/rule_engine.py`): pure `evaluate` +
  explicit `evaluate_observation` persistence, deduped by `(observation_id,
  rule_id)` so retried webhooks never double-alert. Compound metrics
  (systolic/diastolic) read from `measurement_context`; missing values are never
  inferred (FR-019). Threshold evaluation lives only here, never in the LLM.
- Alert lifecycle (`services/alerts.py`): priority-ordered review queue
  (urgent→priority→routine), `acknowledge`/`assign`/`escalate`/`resolve`/`dismiss`
  with terminal-state 409 guards, `escalate` bumps priority to urgent, and every
  disposition writes a `ClinicianAction`. Summary counts for dashboards.
- Hooked into the clinical path: `patients.add_observation` evaluates new
  observations and raises alerts automatically.
- Seeded demonstrator thresholds (pending clinic sign-off): systolic >140/<100,
  glucose >200/<60.
- Endpoints: `GET /alerts/summary`, `GET /alerts` (status/priority/patient/
  assignee filters), `GET /alerts/{id}` (+ action history), alert disposition
  actions, and `GET/POST /safety-rules`, `POST /safety-rules/{id}/deactivate`.
  RBAC: clinical/reception for the queue; owner/doctor for rule writes; finance
  excluded.
- Web: Alerts page (summary stats, priority/status queue, review modal with
  notes + action history, safety-rule list + publish/deactivate) and open/urgent
  alert counts on the dashboard.
- 17 new tests (64 total: 9 rule-engine unit + 8 alerts integration); the real
  migration + seed and a live observation→alert→acknowledge→resolve smoke were
  verified end-to-end; ruff, format, mypy (strict), eslint, tsc, vitest and
  production build all green.

## Increment 8 deliverable

- AI provenance model + migration: `ai_extractions` (patient/message link,
  modality text|vision, model, prompt version, status succeeded|needs_clarification|
  skipped|failed, intent, confidence, clarification question, extracted + raw
  response JSONB, error, observation count) and `observations.ai_extraction_id`
  (nullable FK, ON DELETE SET NULL) linking every AI-derived reading back to its
  analysis record.
- AI service (`services/ai.py`): strict extract-only system prompt with guardrails
  (no diagnosis/dosage/unit inference). A deterministic heuristic extractor runs
  whenever the integration is disabled (no key / `ai_enabled` false), keeping the
  flow fully offline and tests reproducible; the OpenAI path (gpt-4o text + vision
  via `AsyncOpenAI`, lazy import) returns the same normalized result shape. Extracted
  observations are written as ordinary clinical data and then evaluated by the
  deterministic rule engine — thresholds still never depend on the model.
- Inbound hook: `messaging._store_inbound` analyzes new inbound text/image messages
  for known patients right after flush. Unit-less/ambiguous readings persist with
  `needs_clarification` and raise a `clarification` alert; the message is marked
  `needs_clarification`. Unknown senders keep the exception-queue path with no AI.
- Endpoints: `GET /patients/{id}/ai-extractions` (paginated provenance),
  `GET /ai-extractions/{id}`, `POST /messages/{id}/analyze` (manual re-run).
  RBAC: clinical/reception roles; finance excluded.
- Web: patient "AI insights" tab (status/modality/intent, model + prompt version,
  confidence, extracted observations with context, clarification questions,
  failures, and a re-analyze action).
- 18 new tests (82 total: 11 AI service unit + 7 AI integration); ruff, format,
  mypy (strict), eslint, tsc, vitest and production build all green.

## Increment 9 deliverable

- Non-response engine (`services/non_response.py`): deterministic, unit-tested
  `decide_non_response` (`wait`/`remind`/`overdue`) plus `escalation_priority`.
  Only instances that actually reached the patient (SENT/DELIVERED/READ) are
  processed — provider delivery failures are never mistaken for non-response
  (FR-027, AC-007).
- Deadline monitoring + reminders + overdue (FR-022/FR-023/FR-024): when a
  response deadline passes with reminders remaining and the patient remains
  eligible (consent + active schedule), a spaced reminder is re-dispatched and
  the response window restarts; once `max_reminders` is exhausted the instance
  is flagged `OVERDUE` with `overdue_at` for the staff queue. Reminder limits
  come from the schedule's `reminder_policy` (`max_reminders`, `interval_hours`).
- Escalation policy (FR-025): an exhausted, overdue follow-up with
  `escalate_after_deadline` raises a single `non_response` alert at the
  configured `review_priority`, linked to the instance and assigned to the
  responsible staff. Idempotent per instance.
- Delivery-failure handling (FR-027): dispatch (and failed reminders) raise a
  `delivery_failure` alert distinctly from non-response; failed deliveries stay
  visible on the dashboard via the analytics failed-delivery count.
- Human acknowledgement (FR-026): instance `acknowledge` / `assign` / `resolve`
  actions (resolve marks the follow-up skipped, leaving the overdue queue and the
  adherence denominator); overdue non-response alerts use the existing alert
  disposition lifecycle.
- Reusable outbound helper `messaging.send_follow_up_message` shares the
  message + delivery-event persistence between first dispatch, reminders and
  delivery-failure surfacing.
- Endpoints: `POST /schedules/process-non-response`, `POST
  /instances/{id}/acknowledge`, `POST /instances/{id}/assign`, `POST
  /instances/{id}/resolve`. RBAC: clinical/reception; finance excluded.
- Celery Beat `process-non-response` (every 5 min) over a fresh async session.
- Web: Follow-ups operations page gains a "Run non-response" action, a
  reminders/overdue/escalations result banner and per-row acknowledge/resolve
  actions on overdue rows.
- 16 new backend tests (113 total: 11 decision unit + 5 end-to-end integration);
  ruff, format, mypy (strict), eslint, tsc, vitest and production build all green.

## Increment 10 deliverable

- Analytics service (`services/analytics.py`) computing read-only aggregates over
  existing data — no new tables or migration:
  - **Clinic overview (FR-040):** patient totals + category mix, follow-up
    due/completed/overdue (reusing scheduling day counts), failed deliveries,
    pending clarifications, open/urgent alerts, pending observation reviews, AI
    clarifications and open message exceptions.
  - **Daily operations (FR-043):** consolidated, priority-ordered list of patients
    requiring action, merging overdue follow-ups (joined to their schedule type)
    and open alerts, with per-patient reasons.
  - **Adherence (FR-031):** scheduled/completed/overdue/skipped/failed-delivery/
    awaiting counts and a completion rate whose definition (completed ÷ (scheduled
    − skipped − failed deliveries)) is returned with the response so the metric is
    never ambiguous; provider delivery failures are excluded from the denominator
    rather than counted against the patient.
  - **Trends (FR-028/029/030):** dated observation series bucketed by day/week/
    month with average + latest value, verified vs patient-reported counts, missing
    buckets and unit; pure bucketing helpers are unit-tested.
  - **Finance (FR-042):** recorded revenue/refunds/adjustments from posted payments
    kept strictly separate from estimated billed charges, direct costs and
    contribution (per treatment), plus explicit estimator caveats.
- Endpoints (`/api/v1/analytics`): `GET /overview`, `GET /operations`,
  `GET /adherence`, `GET /patients/{id}/trends`, `GET /finance`.
  RBAC: clinical/reception for operational reads; owner/finance only for finance.
- Web: Analytics page (overview stat grid, action list, adherence card, and a
  role-gated financial section with a per-treatment breakdown and notes); patient
  "Trends" tab with metric + granularity selectors and a dependency-free SVG
  `LineChart`; nav + route wiring.
- 15 new backend tests (97 total: 7 bucketing unit + 8 analytics integration) and
  7 new web tests (10 total); ruff, format, mypy (strict), eslint, tsc, vitest and
  production build all green.

## Increment 11 deliverable

- **Production safety gate** (`core/config.py`): when `APP_ENV=production` the
  settings validator refuses to start on placeholder `SECRET_KEY` /
  `MEDIA_SIGNING_SECRET` / `BOOTSTRAP_ADMIN_PASSWORD` / `WHATSAPP_VERIFY_TOKEN`,
  `APP_DEBUG=true`, localhost CORS origins, live AI without an API key, or a
  missing `WHATSAPP_APP_SECRET` / disabled `WHATSAPP_WEBHOOK_REQUIRE_SIGNATURE`
  (the public webhook route is always mounted, so a live deployment must always
  be able to verify signatures). Enforces PRD AC-012 / Risk 8;
  `tests/test_config_safety.py`.
- **Defensive HTTP headers + access logging** (`core/middleware.py`): every API
  response carries `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, and (production) HSTS; a structured
  access-log middleware records method/path/status/duration with the request id;
  `tests/test_security_headers.py`.
- **Celery resilience** (`workers/celery_app.py`, `workers/tasks.py`): late acks
  with failure acknowledgement, worker-lost rejection, task time limits, and
  automatic retry with exponential backoff + jitter on every workflow task;
  Redis visibility window sized beyond the longest task.
- **Safety/failure test matrix** (PRD §15.4): `tests/test_failure_matrix.py`
  documents and asserts the failure catalogue end to end — duplicate webhooks,
  incorrect patient mapping, missing units, invalid readings, withdrawn consent,
  paused schedules, failed outbound delivery (delivery alert), invalid webhook
  signature, and unauthorized/finance access — plus AI-provider-outage and
  AI-disabled fallback unit tests in `tests/test_ai_service.py`.
- **Deployment hardening** (`infra/`): API container `healthcheck` +
  `stop_grace_period`; JSON log rotation for every compose service; Caddy gains
  HSTS and `Permissions-Policy`; CI gains an `infra` job that validates the
  compose file and builds the API + edge images.
- **Operations runbook** (`docs/RUNBOOK.md`): topology, first-time deploy,
  production env safety gate, redeploy, backups/restore, migrations, secrets
  rotation, monitoring, incident playbooks (webhooks, delivery, non-response,
  AI/WhatsApp/postgres outages, disk, rollback), scaling and a security
  checklist; README links to it.
- 26 new backend tests (139 total: 13 config-safety + 2 security-header + 2 AI
  failure + 9 failure-matrix integration); ruff, format, mypy (strict) and the
  full pytest suite all green.

## Post-audit hardening (Phase A)

A static audit of the completed system identified five safety-critical defects;
all five are remediated with regression coverage (backend suite now 155 tests):

- **A1 fail-closed webhook signatures** (`services/whatsapp.py`,
  `api/v1/endpoints/messaging.py`, `core/config.py`): `verify_signature` returns
  `False` when no app secret is configured (it can no longer pass an unverified
  payload), unverifiable webhooks are rejected with **403**, and production
  requires both `WHATSAPP_APP_SECRET` and `WHATSAPP_WEBHOOK_REQUIRE_SIGNATURE`.
  Signature enforcement is the default everywhere; an unsigned payload is
  refused with 403 unless an explicit, non-production-only
  `WEBHOOK_ALLOW_UNSIGNED` opt-out is enabled (never permitted in production),
  in which case the request is still recorded with `signature_verified=false`.
- **A2 send-time eligibility** (`services/messaging.py`, `services/schedules.py`,
  new `follow_up_instances.skip_reason` column + migration `d4a1b2c3e5f6`):
  eligibility is re-checked at dispatch, and a queued instance whose consent was
  withdrawn or whose patient became inactive is marked `SKIPPED` with an
  auditable reason instead of being sent. `_is_eligible` now also requires an
  `ACTIVE` patient status.
- **A3 delivery-vs-non-response** (`services/messaging.py`,
  `services/non_response.py`, `services/analytics.py`): a provider `failed`
  status event reconciles the linked instance to `FAILED` and raises a
  delivery-failure alert; a rejected reminder returns failure and **never**
  advances `reminder_count`/deadline; `process_non_response` reports
  `reminders_failed`; adherence excludes delivery failures from the denominator.
- **A4 refund validation** (`services/finance.py`): refunds require a
  `related_payment_id` pointing at an earlier *payment* for the *same* patient,
  may not exceed the refundable balance (net of prior refunds), and only refunds
  may reference an earlier payment.
- **A5 AI validation gate** (`services/ai.py`): `validate_observation` rejects
  out-of-range, unit-less, unknown-unit, unsupported-type and reversed/
  incomplete blood-pressure readings before persistence; rejected readings are
  not stored and raise a clarification alert instead.

## Post-audit hardening (Phase B)

A second review of the Phase A work identified remaining correctness/safety
gaps. They are remediated as follows (backend suite now 163 tests):

- **B1 ambiguous-sender matching** (`services/messaging.py`,
  `models/messaging.py`, migration `e5b2c3d4f6a7`): an inbound message is
  matched on the last ten digits; when more than one patient matches, an exact
  normalized-number match is preferred, and a genuinely tied sender is
  quarantined as a new `ambiguous_sender` exception with the candidate ids
  instead of being attached to an arbitrary record.
- **B2 send-once claim** (`services/messaging.py`, `services/non_response.py`):
  queued instances and pending reminders are claimed with
  `SELECT … FOR UPDATE SKIP LOCKED`, so concurrent dispatchers (Beat plus a
  manual dispatch, or two workers) never send the same row twice.
- **B3 readiness truth** (`api/v1/endpoints/health.py`,
  `infra/docker-compose.yml`): `/health/ready` now returns **503** when a
  dependency is degraded, and the container health check probes readiness.
- **B4 AI off the request path** (`workers/tasks.py`, `services/ai_queue.py`,
  `services/ai.py`, `core/config.py`): inbound analysis is enqueued as a Celery
  task; production requires `AI_PROCESSING_MODE=deferred`, and the task retries
  until the webhook's row has committed. `inline` remains the dev/test default.
- **B5 explicit webhook opt-out** (`core/config.py`, `services/whatsapp.py`):
  signatures are required by default; an unsigned payload is rejected with 403
  unless the non-production-only `WEBHOOK_ALLOW_UNSIGNED` opt-out is enabled
  (refused in production).

## WhatsApp completeness (Phase C)

A focused audit of the WhatsApp integration found the inbound path largely
complete but several outbound/media/ops pieces missing. They are now
implemented (backend suite now 180 tests; web suite 15):

- **C1 session-window-aware outbound** (`core/config.py`,
  `services/messaging.py`, `services/non_response.py`, `services/whatsapp.py`):
  Meta allows free-form text only within 24 hours of the patient's last inbound
  message. With `WHATSAPP_ENFORCE_SESSION_WINDOW=true`, dispatch and reminders
  send an **approved, active template** outside the window (positional
  parameters derived from the shared `{{placeholder}}` context) and record a
  clear `template_required` failure — instead of sending text Meta rejects with
  error 131047 — when no usable template is configured. Production requires the
  flag when `WHATSAPP_ENABLED=true`.
- **C2 media persistence + signed serving** (`services/media.py`,
  `services/media_queue.py`, `workers/tasks.py`,
  `api/v1/endpoints/media.py`): inbound media bytes are downloaded by a Celery
  worker and stored under `MEDIA_ROOT`; staff view them through short-lived
  HMAC-signed URLs (`GET /api/v1/media/{id}?token=…`, TTL
  `MEDIA_URL_TTL_SECONDS`) that never expose the provider id or a bare file
  path. `MessageRead.media_url` carries the link and the patient conversation
  tab renders it.
- **C3 exception review UI** (`web/src/routes/MessageExceptionsPage.tsx`): the
  staff exception queue (`/messages/exceptions`) now has a page — filter by
  status, inspect reason/details, and resolve or dismiss with notes — wired into
  the sidebar navigation.
- **C4 test isolation** (`tests/conftest.py`): the suite pins WhatsApp to
  dry-run defaults so a developer's live Meta credentials in `.env` can never
  trigger real network sends or change the webhook verify token during tests.

## WhatsApp: media + vision made real (Phase D)

Phase C stored media and called the AI path "vision", but two defects meant
inbound photos were never actually analysed: every async Celery task was
silently failing, and the analysis path re-downloaded media from Meta (or, when
that failed, captioned the message and recorded a `vision` success without
reading the image). Phase D fixes both and is the state frozen for evaluation
(backend suite now **199** tests; web **28**).

- **D1 worker event loop** (`workers/tasks.py`): each task called
  `asyncio.run()`, building and tearing down a fresh loop per task. The lazily
  created SQLAlchemy engine and cached async Redis client keep pooled
  connections bound to the loop that opened them, so a later task ran on a dead
  loop and failed (`NoneType…send`, `Event loop is closed`). Every async task
  was affected — which is why inbound media was never downloaded. Now one
  process-wide loop is shared by all tasks.
- **D2 OpenRouter-compatible gateway** (`core/config.py`, `services/ai.py`):
  `openai_base_url` makes the client target any OpenAI-compatible host; without
  it always hit `api.openai.com` and 401'd against a non-OpenAI key.
- **D3 vision reads stored media** (`services/ai.py`): analysis reads the file
  the media worker already persisted under `MEDIA_ROOT`, falling back to a
  provider download. Reuses bytes already paid for and survives provider
  media-expiry.
- **D4 fail loudly** (`services/ai.py`): with no image bytes the call raises and
  the message is marked `FAILED`, instead of silently captioning the text and
  recording a false `vision` success. Provider and media failures are now
  visible in the queue rather than hidden.
- **D5 prompt v2** (`services/ai.py`): the prompt never listed the observation
  vocabulary the validator accepts, so the model invented type names (`sugar`,
  `bp`) which were then rejected as unsupported and the reading dropped. The
  prompt now enumerates the canonical types and units, common aliases are
  folded by `_normalize_observation_type`, and `PROMPT_VERSION` is
  `extraction-v2`.
- **D6 AI test isolation** (`tests/conftest.py`): the suite pins AI off and
  inline, so a developer's live provider key in `.env` can never be spent or
  slow the suite down.
- **D7 media rendered everywhere** (`web/src/components/MediaAttachment.tsx`,
  `schemas/analytics.py`, `services/analytics.py`): one shared signed-URL
  component with thumbnail/full modes, a download link for non-images, and a
  quiet `Media unavailable` fallback, used by the patient conversation, the
  replies inbox and thread, and a new compact thumbnail on the WhatsApp
  overview. `OverviewMessage` gained `media_mime_type` and a computed
  `media_url`.
- **D8 single scheduler**: `LOCAL_SCHEDULER_ENABLED=false` retires the
  in-process scheduler so Celery Beat is the only one, removing a duplicate-run
  risk in production.

## Evaluation and freeze

Phase D was followed by a deliberate stop-and-evaluate before further feature
work. Findings, evidence and the ops root cause for the earlier silent stack
deaths are written up in **[EVALUATION.md](./EVALUATION.md)**. The frozen state
is tagged `freeze/whatsapp-2026-10-18` and pushed to the project remote.

## AI auto-reply with clinical escalation (Phase E)

Phase D taught the system to *read* a patient's message. Phase E makes it
*answer* — bounded, reversible, and always downstream of the deterministic rule
engine. The engine still decides what a reading means; the model only writes the
WhatsApp sentence that reports that decision back. Backend suite now **230**
tests; web **32**.

Design questions settled before a line was written: the doctor is notified over
**WhatsApp** at the number held in settings; replies are **LLM-generated per
message** (no templates); the feature is a **database setting with a Settings
screen**, not an env flag, so it is reversible without a deploy; only
**readings and clarification questions** are answered — greetings and open
questions are left to staff; and "critical" means **`urgent`-priority rules
only**.

- **E1 two tables** (`models/settings.py`, `models/auto_reply.py`, migration
  `d4e5f6a7b8c9`): `app_settings` for clinic-tunable key/value switches, and
  `auto_replies` — one row per decided message, UNIQUE on `source_message_id`
  so a retried worker or a manual re-analysis can never message a patient twice
  about one reading. Both setting rows are seeded **disabled**; nothing sends
  until a clinician switches it on.
- **E2 settings service and API** (`services/settings.py`,
  `api/v1/endpoints/settings.py`): a curated registry owns each setting's type,
  default, description and normaliser, so an unknown or wrongly-typed key can
  never be persisted. Writes are limited to OWNER/DOCTOR — a toggle is as
  consequential as a threshold — and are audit-logged as `setting.updated`.
  `bool("false")` is `True` in Python, so booleans are validated by type, not
  coerced.
- **E3 Settings screen** (`routes/SettingsPage.tsx`, `/settings`): the
  auto-reply switch and the doctor's number, with client-side E.164 validation
  mirroring the server, and an explicit note that urgent findings are what
  reach the doctor.
- **E4 decision engine** (`services/auto_reply.py`): a fixed mode table —
  readings with an alert → `out_of_range_reading`, readings without →
  `safe_reading`, no reading but a clarification question → `clarification`,
  anything else → silence. The payload handed to the model is built from the
  stored observation and the rule engine's own reason string, never from the
  model's reading of the patient's words, and carries the last six messages for
  context.
- **E5 curated prompt and generator** (`auto-reply-v1`): ten hard rules —
  use only the supplied facts, no diagnosis, no medication advice, no invented
  numbers, no reassurance about an out-of-range reading, urgent says only that
  the care team has been informed, 240 characters, never claim to be an AI,
  never advise delaying care. **There is no template fallback**: with no
  provider key the reply fails closed and is recorded as `failed`.
- **E6 delivery as its own tasks** (`workers/tasks.py`,
  `services/auto_reply_queue.py`): `generate_auto_reply` and
  `notify_doctor_of_critical_reading` are separate Celery tasks so a send
  failure can never roll back the observation or the alert that already
  succeeded, and so an unreachable doctor number can never take back a message
  the patient already received. Analysis enqueues the reply only when the
  feature is on; a broker outage is logged and swallowed, so the safety path
  never depends on it.

Safety properties worth stating plainly: the alert is raised by the rule engine
*before* any model is called, so an outage costs a reply, never a page; expected
failures are written to the `auto_replies` row instead of raised, so the urgent
notification still commits alongside a failed reply; the doctor notification is
idempotent on `doctor_notified_at` and runs as its own task; and one reply per
patient per 60 seconds suppresses bursts without ever suppressing the urgent
page, which is recorded on a `suppressed` row rather than dropped.

## Remaining increments (planned)

All planned increments (1–11) are complete, and the Phase C, D and E gaps above
are closed. Further work is driven by the PRD's open questions (approved
thresholds, live WhatsApp/AI enablement, financial inputs, media retention
policy) and by operational feedback once the clinic goes live. Known
non-blocking follow-ups are tracked in [EVALUATION.md](./EVALUATION.md) §8 —
outbound retry/backoff for transient provider errors, interactive/outbound
media composition, the documented coverage gaps, and the Phase E follow-ups
(prompt tuning against real patient language, per-clinician notification
routing beyond the single configured number, a UI view of the `auto_replies`
audit trail, and a review of the 60-second reply cooldown once real traffic
exists).

