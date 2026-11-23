# Implemented-feature checklist

Legend: ✅ implemented & tested · 🟡 implemented, partially tested / limited (see LIMITATIONS.md) · ⬜ not implemented (integration path documented)

Test files: `auth` = tests/test_auth_vault.py · `research` = tests/test_research.py · `pbs` = tests/test_pipeline_budget_scheduler.py · `api` = tests/test_api_endpoints.py

## Milestone 1 — Working foundation
| Feature | Status | Evidence |
|---|---|---|
| New repository, FastAPI backend, React/TS/Vite/Tailwind frontend | ✅ | builds clean; UI verified in a real browser (desktop + 390 px mobile) |
| SQLite DB + Alembic migrations (PostgreSQL-ready types) | ✅ | `pbs::test_migrations_match_models`, `test_migration_downgrade_and_upgrade` |
| Owner account: Argon2id, password policy, lockout, rate limit, optional TOTP | ✅ | `auth::test_setup_once…`, `test_login_lockout…`, `test_totp_flow`, `test_passwords_and_pins_are_argon2id_hashed` |
| Server-side sessions, idle + absolute expiry, CSRF | ✅ | `auth::test_session_*`, `test_csrf_required_for_mutations` |
| Seven business workspaces (overview, research feed, pipeline, CRM, tasks, financials, recommendations, reports, automation) | ✅ | `api::test_workspace_endpoints`; UI tabs |
| Private vault: PIN 2653 (hashed), change PIN, throttling/lockout, per-session unlock, 15-min idle lock, manual lock, lock on logout | ✅ | `auth::test_*vault*`, `test_change_pin`, `test_wrong_pin…`, `test_vault_unlock_is_per_session` |
| Private data excluded everywhere when locked (19 endpoints incl. aggregates, search, exports, briefings, costs) | ✅ | `auth::test_no_private_leakage_when_locked`, `test_aggregates_exclude_private_when_locked` |
| Mac launcher (`START-MAC.command`): Python check, venv, deps, .env, migrations, browser, LAN/Tailscale address, graceful stop | 🟡 | exercised on Linux with macOS command shims; not run on a physical Mac |
| Windows launcher | 🟡 | written, not executed |
| Initial dashboard | ✅ | screenshots verified |

## Milestone 2 — Research infrastructure
| Feature | Status | Evidence |
|---|---|---|
| Persistent scheduler, schedules, jobs, retries w/ exponential backoff, non-retryable failures | ✅ | `pbs::test_retry_with_backoff_then_fail`, `test_non_retryable_fails_immediately` |
| Restart recovery, stuck-job (heartbeat) recovery, missed-run coalescing | ✅ | `pbs::test_restart_recovery…`, `test_stuck_job…`, `test_schedule_enqueues_and_missed_runs_coalesce` |
| Job cancellation (queued and running) | ✅ | `pbs::test_cancel_queued_and_running` |
| Job marked succeeded only on real completion (partial work rolled back) | ✅ | `pbs::test_job_success_only_when_handler_returns`, `research::test_retrieval_failure_is_recorded…` |
| Source adapters: Socrata datasets, Socrata discovery, USAspending, SAM.gov, RSS | ✅/🟡 | `research::*` (SAM.gov mocked only) |
| Polite HTTP: per-host rate limits, backoff, caching, size cap | ✅ | used by all adapters |
| Evidence storage (source records, entity checks, verification, AI analysis labelled) | ✅ | `research::test_full_pipeline…`, `test_ai_enrichment…` |
| AI extraction for unstructured text (structured JSON, injection isolation) | ✅ (mocked provider) | `research::test_ai_enrichment_marks_output_as_ai…` |
| Deduplication + change tracking | ✅ | `research::test_rerun_dedupes_and_tracks_changes` |
| Scoring + automatic qualification/rejection + pipeline insertion | ✅ | `research::test_full_pipeline…` |
| Per-stage audit trail per run | ✅ | ResearchEvent assertions |

## Milestone 3 — National asset recovery
| Feature | Status | Evidence |
|---|---|---|
| 51-jurisdiction registry (agency, portals, all rule fields, citations, review status, operating status) | ✅ | `pbs::test_jurisdiction_verification…` (51 rows) |
| Official source framework: weekly portal reachability/change checks; rules require owner-added citation to verify; clearing requires verification | ✅ | `api::test_portal_check…`; live run: 38/51 reachable, 7 bot-blocked, 6 seed URLs corrected |
| Legal rule content for each state | ⬜ | intentionally blank until researched — see LIMITATIONS |
| Working public-data integrations (Austin, College Station, Providence, Montgomery County MD) | ✅ | live run: 668 verified corporate records, 14 qualified |
| Corporate-only filtering, entity merge, Texas registry verification | ✅ | `research::test_full_pipeline…` |
| Economics: value × permitted/assumed fee × success probability − cost (never value-as-revenue) | ✅ | `pbs::test_scoring_uses_verified_fee_cap` |
| Compliance alerts + outreach blocking until jurisdiction verified & cleared and entity confirmed | ✅ | `research::test_compliance_blocks_outreach…`, `pbs::test_api_approval_blocked_by_compliance` |
| Re-verification of records (closes claimed/removed records) | ✅ | `research::test_reverification…` |
| Automated research runs | ✅ | `pbs::test_full_cycle_with_mocked_sources`; live cycle executed |

## Milestone 4 — Executive intelligence
| Feature | Status | Evidence |
|---|---|---|
| Automated briefings after each cycle answering the 7 questions; public + private variants; no fabricated activity | ✅ | `pbs::test_full_cycle…` (empty cycle → "No new opportunities") |
| Optional AI briefing summary grounded in stored facts | 🟡 | code path implemented; requires API key |
| Pipeline analytics (stage funnel, values) | ✅ | `/api/pipeline/summary` |
| Approval system: exact action, justification, evidence, benefit, risks, cost; hash-confirmed, single-use, expiring | ✅ | `pbs::test_approval_flow_single_specific_action`, `test_tampered…`, `test_expired…` |
| Financial reporting: actuals vs forecasts vs pipeline estimates (never mixed), by business & portfolio, monthly chart, CSV | ✅ | `pbs::test_finance_actuals_never_include_estimates` |
| AI budget enforcement (daily, monthly, per-job, requests/hour, hard/soft), caching, model routing, cost ledger | ✅ | `pbs::test_budget_*` |
| Worker monitoring (heartbeats, health page) | ✅ | `/api/system/health` |
| Backup / restore | ✅ | `pbs::test_backup_and_restore_roundtrip` |

## Milestone 5 — Portfolio expansion
| Feature | Status | Evidence |
|---|---|---|
| Commercial permits: Chicago (>$250k), Seattle non-residential; public-record contacts | ✅ | live run: 283 permits; `research::test_permit_contacts…` |
| Liquidation: Texas WARN closure signals | 🟡 | live run: 10 notices; auctions/bankruptcy not integrated |
| Procurement: USAspending expiring-contract recompete windows; SAM.gov solicitations (key required) | ✅/🟡 | live run: 88 awards |
| State/municipal procurement portals | ⬜ | see LIMITATIONS |
| Private ventures: workspaces, CRM, tasks, finance, RSS market intel (proposed feeds), compliance notes | 🟡 | no venture-specific data sources enabled by default |
| Source discovery for new datasets (proposed, owner-enabled) | ✅ | `research::test_source_discovery…` |
