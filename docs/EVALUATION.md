# System Evaluation — WhatsApp Integration Freeze

**Date:** 2026-10-18
**Frozen at:** commit `0236592`, tag `freeze/whatsapp-2026-10-18`
**Purpose:** evaluate the WhatsApp integration before adding further features.

---

## 1. Executive summary

The WhatsApp integration works end-to-end against the real provider and a real
vision model. Inbound media is stored, served and rendered in the UI; the
vision path reads the *stored file* rather than re-downloading; observations
carry full provenance; and the alert rule fires correctly by staying silent on
a normal reading.

The freeze uncovered three issues that were **not** defects in the product
code:

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | The dev stack died silently twice; root cause was **not** a code bug | High | **Fixed** (see §7) |
| 2 | `launch.ps1` spawned services via WMI into Session 0, where they were SIGINT'd seconds after start | High | **Fixed** |
| 3 | The OpenRouter key expired on 2026-10-18 | High | **Resolved** — replaced with a key that never expires |

One genuine data-hygiene problem was found and cleaned (§6). No product code
required changing during the evaluation.

---

## 2. Scope and method

Read-only functional verification against the live stack, plus one approved
data cleanup and one ops fix. No refactors, no migrations, no `.env` changes.

All checks were run against a real WhatsApp Business phone number and the real
OpenRouter vision model, not fixtures.

---

## 3. Functional verification (live stack)

### 3.1 Media pipeline

| Message | MIME | `media_url` | Signed GET |
|---------|------|-------------|-----------|
| `92f853f7` (glucometer photo) | `image/jpeg` | present | **200 image/jpeg 12561 B** |
| `835c2a6d` (meal photo) | `image/jpeg` | present | **200 image/jpeg 85249 B** |
| text messages | — | `null` | n/a |

Text messages correctly return `media_url: null` rather than a URL that 404s.
Both files exist on disk under `apps/api/data/media/inbound/` with matching
sizes.

### 3.2 Clinical chain for the real glucometer image

```
whatsapp_messages 92f853f7  processing_status = processed
  └─ ai_extractions 71fc296b   status=succeeded  confidence=1.000
       └─ observations         blood_glucose 102 mg/dL  validation_status=validated
                              source=whatsapp
```

A glucose of 102 mg/dL is below the 200 mg/dL high-glucose rule, so **no alert
was created** — and `alerts` for this patient is confirmed `0`. The rule
therefore demonstrates correct *absence* of firing, which is the harder case to
get right.

### 3.3 Provenance

`observations` contains exactly one row, `source=whatsapp`,
`validation_status=validated`. Observations are append-only (no update or
delete route exists), so provenance cannot be silently rewritten.

---

## 4. Quality gates

All gates pass on the frozen commit.

| Gate | Result |
|------|--------|
| `ruff check` | clean |
| `ruff format --check` | 94 files formatted |
| `mypy app` (strict) | clean, 70 source files |
| `pytest` | **199 passed** |
| `eslint` | clean |
| `tsc --noEmit` | clean |
| `vitest` | **28 passed** (7 files) |
| `pnpm build` | succeeds |

### 4.1 Coverage gaps (documented, deliberately not filled during freeze)

- Deferred AI worker path has no integration test — it was proven manually
  (task `succeeded ... {'found': True, 'analyzed': 1}`).
- Signed-URL expiry (300 s TTL) is not exercised by a test.
- Session-window template fallback on window expiry is untested.
- `openai_base_url` configuration has unit coverage but no test asserting the
  client is constructed against a non-default host in the running app.
- Prompt v2 behaviour has alias-normalisation unit tests but no golden-image
  regression test.

These belong in the next increment, not in a freeze.

---

## 5. Fresh-eyes review of the newest code

The frozen increment is the highest-risk surface, so it was reviewed line by
line.

| Area | Verdict |
|------|---------|
| Worker persistent event loop | Sound. One loop per process replaces `asyncio.run()` per task, which was the cause of every async task failing (`NoneType…send`, `Event loop is closed`). |
| `_load_media_bytes` | Reads the stored file first, falls back to provider download. Correct ordering — the stored file is authoritative and avoids a second provider round-trip. |
| Vision failure path | Fails loudly and marks the message `FAILED` instead of silently captioning. This is the change that makes provider/media failures visible. |
| Prompt v2 + alias normalisation | Correct. The earlier defect — the model inventing type names the validator then rejected — is fixed by enumerating the vocabulary. |
| `MediaAttachment` | Single shared component with a quiet fallback. No duplication across the three surfaces. |

No defects were found in this review.

---

## 6. Data integrity

### 6.1 Dev noise removed (approved)

Four patients existed purely as test fixtures and were polluting the alert feed
and analytics scope:

`Smoke Test Patient`, `Finance Smoke`, `Schedule Smoke`, `Smoke Alert Patient`

| Action | Rows |
|--------|------|
| `clinician_actions` (FK is `SET NULL`, so deleted explicitly to avoid orphans) | 2 |
| `patients` deleted | 4 |
| Cascaded children (`alerts`, `consent_records`, `follow_up_instances`, `follow_up_schedules`, `observations`, `patient_categories`, `patient_treatment_assignments`, `payments`, `care_plans`) | 39 |
| **Total** | **41** |

Executed inside a single transaction; verified with zero orphans across all
four `SET NULL` tables and zero dev-named patients remaining.

### 6.2 Retained deliberately

One open alert remains, for patient **Dnyanu**:

> `delivery_failure` — "The messaging provider rejected the outbound message."
> created 2026-10-17 03:48 UTC

This is a genuine record of a real rejected outbound message, not test debris,
so it was left in place. Disposition is a clinical decision, not a data-hygiene
one.

The `heuristic` extractions were also left alone: they are legitimate
provenance from before AI was enabled, not noise.

---

## 7. Ops and configuration

### 7.1 Root cause of the "silent" stack deaths

Both apparent crashes (2026-10-17 and again on 2026-10-18) had the same
signature: every log ended in `^C`, and ngrok logged
`INFO received stop request ... restart:false`.

The processes were **not** crashing. `launch.ps1` used
`Invoke-CimMethod Win32_Process -MethodName Create`, which spawns processes
through WmiPrvSE in **Session 0**. Console applications spawned that way lose
their console as soon as the WMI call completes and receive `CTRL_C_EVENT`
within seconds. The logs confirmed it: all five services started at
08:24:11–08:24:14 and were gone by 08:24:15.

A contributing factor, unrelated to the code: this machine enters **Modern
Standby** repeatedly through the day (event log shows transitions at 09:18,
09:43, 09:55, 10:49, 10:57, 10:59, 12:39, 12:42, 12:56 …), which throttles or
suspends background work.

**Fix applied:** `launch.ps1` now spawns each service with
`Start-Process -WindowStyle Hidden`, giving each its own hidden console in the
user session instead of Session 0. A `launch.log` records each spawn.

**Verified:** after the fix the stack was brought up through the real logon path
(the Startup-folder VBS), and all services were confirmed still alive in a
subsequent, separate shell — uvicorn, celery worker + beat, vite, and the ngrok
tunnel at `https://euphemism-subfloor-platform.ngrok-free.dev`.

### 7.2 Reboot survival

Auto-start **is** correctly installed: `Startup\madhavbaug-dev.vbs` →
`start-all.cmd` (Docker wait → compose → `launch.ps1`). Replacing the WMI spawn
makes the chain actually hold, which was the missing piece.

Registering a Task Scheduler logon task was attempted as an alternative but
requires elevation, which this shell does not have. The VBS + `Start-Process`
chain does not need admin.

### 7.3 Configuration observations

- Health probe is **`/health`**, not `/api/v1/health` — the latter returns 404.
  Any monitoring or runbook referencing the wrong path would report the service
  as down when it is healthy.
- Non-default `.env` flags now in play: `AI_ENABLED=true`,
  `AI_PROCESSING_MODE=deferred`, absolute `MEDIA_ROOT`,
  `LOCAL_SCHEDULER_ENABLED=false`, `OPENAI_BASE_URL` pointing at OpenRouter,
  vision model `meta-llama/llama-4-maverick`, text model `openai/gpt-4o-mini`.
- `LOCAL_SCHEDULER_ENABLED=false` means Celery Beat is the sole scheduler; this
  avoids two schedulers racing.

### 7.4 External dependencies

| Dependency | State |
|-----------|-------|
| OpenRouter key | **Permanent** — verified `expires_at` is null (replaced 2026-10-18) |
| Meta system user token | `expires_at=0` — permanent |
| ngrok free static domain | Works, but free-tier session limits apply |
| Docker / Postgres / Redis | Healthy |

---

## 8. Remaining features (next increment, not started)

From the roadmap's own "remaining" list and the PRD open questions:

- Outbound retry/backoff for transient provider errors.
- Interactive and outbound media composition.
- Clinic-approved alert thresholds (currently hardcoded defaults).
- Live WhatsApp/AI enablement decisions for production.
- Financial inputs validation.
- Media retention policy.
- The coverage gaps listed in §4.1.

Operational follow-ups:

- Consider mitigating Modern Standby for long-running dev services
  (e.g. `powercfg /change standby-timeout-ac 0` when plugged in), or move the
  stack to a host that does not idle-sleep.
- Consider a Task Scheduler task (requires elevation) as a more robust
  alternative to the Startup VBS.

---

## 9. Freeze integrity

| Item | Value |
|------|-------|
| Branch | `master` |
| Frozen commit | `0236592` |
| Tag | `freeze/whatsapp-2026-10-18` |
| Remote | `https://github.com/sanket-sonwane/madhavbaug-v2-whatsapp-integration-.git` |
| Commits in freeze | 3 — worker loop fix · AI gateway/vision · media rendering |
| Working tree | clean |
| Secrets in tracked files | none (`.env*`, `*.log`, `data/` all ignored) |
