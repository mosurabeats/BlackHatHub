# Architecture

## Decisions

| Concern | Choice | Why |
|---|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic | Requested baseline; typed, testable |
| Database | SQLite (WAL) by default; PostgreSQL via `EXECHUB_DATABASE_URL` | Zero-install on the Mac; portable types (`UTCDateTime`, JSON) keep PG migration a config change |
| Scheduler | Custom DB-backed scheduler (`app/jobs/scheduler.py`) in the server process | Persistent job state, restart recovery, missed-run coalescing, retries and cancellation that are fully unit-testable. APScheduler was not used because its job store does not model per-run status/attempts/heartbeats, which the reliability requirements need. |
| Workers | Thread pool (default 2) in the same process | No Redis/Celery to operate; research is I/O-bound |
| Frontend | React 18 + TypeScript + Vite + Tailwind, shipped prebuilt in `frontend/dist` | Owner never needs Node.js |
| AI | Official Anthropic SDK and OpenAI SDK behind one `complete_json` gateway | Structured JSON outputs, budget checks, caching, cost ledger |
| Auth | Username + Argon2id password, optional TOTP, server-side sessions, CSRF tokens | Strong single-owner authentication |

## Layout
```
backend/app/
  main.py, server.py        app factory (middleware, routers, SPA), uvicorn entry
  config.py, db.py          settings (.env), engine/session, UTC datetime type
  models.py                 ORM (26 tables) — see "Data model"
  security.py, deps.py      Argon2id, tokens, rate limiter, redaction; auth/CSRF/vault/scope dependencies
  privacy.py                Scope: the ONLY way business-scoped queries pick business ids
  pipeline.py               Pipeline Manager rules + approval service
  research/                 engine.py (stages), http.py (polite client), normalize.py, verifiers.py
    adapters/               socrata (unclaimed property, permits, WARN), socrata_catalog (discovery),
                            usaspending (recompetes), samgov (solicitations), rss (market intel)
  agents/                   scoring (Opportunity Analyst), compliance (Compliance Analyst),
                            monitor (stale/reverify/requalify/portal checks/source discovery), executive (briefings)
  ai/                       client (gateway + injection isolation), budget (Cost Controller), pricing
  jobs/                     scheduler + handlers (Research Director cycle etc.)
  api/                      auth, core (businesses/pipeline/CRM/tasks/approvals), research, portfolio
  seed.py, jurisdictions_data.py   businesses, vault, 51 jurisdictions, sources, schedules
backend/alembic/            migrations (0001 initial schema)
frontend/src/               pages/*, components/*, api.ts (CSRF + background polling header)
```

## Research engine
Each research run (`ResearchRun`) writes a `ResearchEvent` for every stage:

1. **Discover** — Source Discovery Agent queries the Socrata Discovery API and *proposes* datasets (disabled until you map fields and enable).
2. **Retrieve** — adapter fetches via `ResearchHttp` (per-host rate limit, exponential backoff on 429/5xx/network errors, response cache, 25 MB cap). 401/403 become non-retryable *limitations* recorded on the run and source.
3. **Parse / Extract** — deterministic field mapping per profile; individuals are excluded from asset recovery (corporate-only heuristic). Unstructured items (RSS) are analysed by the AI Research Analyst when configured and within budget; otherwise kept at low confidence.
4. **Verify** — records from official publishers are marked `source_record_official`; Texas entities are checked in bulk against the Comptroller franchise-tax open dataset (match = positive evidence; no match ≠ dissolved). Monitoring re-queries each record by id later (`reverify`) and closes opportunities whose records disappear.
5. **Deduplicate** — fingerprint per business (`entity` mode merges multiple rows for one owner/holder; `record` mode per row). Re-runs update tracked fields and write `updated` history with before/after values.
6. **Score** — `agents/scoring.py`, explainable breakdown; all money outputs are estimates with a written basis.
7. **Qualify** — discovered → researching → verified → qualified, or auto-rejected (`lost`) with reason.
8. **Insert** — opportunity + evidence (content-hashed) + public-record contacts + history.
9. **Monitor** — `pipeline_maintenance`: stale detection, requalification, re-verification.
10. **Recommend** — Pipeline Manager files approval requests for top compliant opportunities; blocked ones get owner tasks listing the blockers; monitoring-type categories get watch tasks.

A run is `succeeded` only if all stages complete; `partial` if limitations were recorded; jobs are `succeeded` only when the handler returns (exceptions roll back partial work).

## Agents (logical roles, shared infrastructure)
| Role | Implementation | AI? |
|---|---|---|
| Research Director | `research_cycle` job: enqueues enabled sources by business priority, then maintenance + briefing | No |
| Source Discovery | `monitor.discover_sources` + `socrata_catalog` adapter | No |
| Research Analyst | engine extract/verify; AI only for unstructured text | Optional |
| Compliance Analyst | `agents/compliance.py` rules, alerts, blockers | No |
| Opportunity Analyst | `agents/scoring.py` | No |
| Pipeline Manager | `pipeline.py` rules, `recommend_actions`, stale/requalify | No |
| Executive Analyst | `agents/executive.py` deterministic briefing + optional AI summary of those facts | Optional |
| Cost Controller | `ai/budget.py` checks before every call; `ai_usage` ledger | No |

AI never has tools and never decides stage changes or approvals; deterministic code consumes its schema-validated JSON.

## Security model
* **Auth**: Argon2id (m=64 MiB, t=3, p=4) passwords; password policy; per-IP login rate limit; account lockout after 5 failures; optional TOTP; session cookies are random 256-bit tokens stored only as SHA-256, `HttpOnly`, `SameSite=Strict`; 12 h absolute / 2 h idle expiry; CSRF token header on all mutations.
* **Vault**: PIN is Argon2id-hashed; unlock state lives on the *session row*; 15-minute inactivity auto-lock (background polling sends `X-Background: 1` and does not count as activity); manual lock; lock on logout and on PIN change; 5-failure lockout + rate limit. Every business-scoped query goes through `Scope.ids`; private objects return 404 (indistinguishable from nonexistent). Private-inclusive briefings are stored separately; AI cost for them is attributed to a private business so locked totals exclude it. Tested by `test_no_private_leakage_when_locked` across 19 endpoints and `test_aggregates_exclude_private_when_locked`.
* **Network**: middleware rejects any client outside loopback / RFC1918 / link-local / Tailscale ranges. Security headers (CSP, frame deny, no-referrer, nosniff). API responses `no-store`. Generic 500s (no stack traces).
* **Untrusted content**: retrieved text is wrapped in `<untrusted_document>` with tag-escaping; the system prompt forbids following embedded instructions; outputs are schema-validated; RSS with DTD/entities is refused; CSV exports neutralise formula injection.
* **Secrets**: API keys only in `.env` (never in DB/API responses); audit details are recursively redacted.
* **Approvals**: hash of (action type, exact text, payload); owner must echo the hash to approve; expires in 14 days; single use (`executed` consumes it); `assert_authorized` is the gate any future executor must call; compliance blockers are re-evaluated at decision time.

## Data model (main tables)
`users`, `auth_sessions`, `vault_config`, `businesses`, `sources`, `research_runs`, `research_events`,
`opportunities`, `opportunity_history`, `evidence`, `contacts`, `tasks`, `approvals`, `jurisdictions`,
`compliance_alerts`, `financial_entries` (actuals only), `forecasts` (owner estimates), `ai_usage`, `ai_cache`,
`jobs`, `schedules`, `worker_heartbeats`, `briefings`, `notifications`, `audit_logs`, `settings`.
Speculative values (`opportunities.estimated_value/expected_value`) and actuals (`financial_entries`) are separate tables and never summed together.
