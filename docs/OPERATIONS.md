# Operations

## Daily use
* **Dashboard** — what's new, top opportunities, approvals, alerts, actual financials, AI spend, system health.
* **Approvals** — read the exact action, tick the confirmation, approve or reject. Approved actions are carried out by you (no outbound integrations are enabled); record the result with *Mark executed*.
* **Jurisdictions** — the asset-recovery gate. For each state you intend to operate in: research the statute/agency guidance, fill the fields, add an official citation, *Mark verified*, then *Clear for operation*. Until then, outreach approvals in that state stay blocked.
* **Research & Sources** — run sources on demand, review *proposed* datasets found by discovery, map their columns and enable them.
* **Briefings** — generated after every research cycle (default every 12 h).

## Schedules (System → Schedules)
| Schedule | Default |
|---|---|
| Research cycle (all sources → maintenance → briefing) | every 12 h |
| Jurisdiction portal checks (51) | weekly |
| Source discovery (per business) | weekly |
| Database backup | daily |

If the Mac was off, each overdue schedule runs **once** on startup (missed count shown). Jobs interrupted by a shutdown are re-queued automatically.

## Backups & restore
* Automatic daily backups (30 kept) in `data/backups/`; *System → Backups → Back up now* for manual ones.
* Restore from the UI (password required) or CLI. A safety backup of the current state is taken first.
* Copy `data/backups` to another disk/iCloud occasionally; the database is the only stateful file (plus `.env`).

## CLI (run from `backend/` with `../.venv/bin/python`)
```
python -m app.cli init                 # migrate + seed
python -m app.cli backup | list-backups | restore <name>
python -m app.cli reset-password <user> # if you forget your password (host access required)
python -m app.cli reset-pin             # reset the vault PIN (host access required)
python -m app.cli run-cycle             # one full research cycle without the web server
python -m app.cli run-source b07.college_station_unclaimed
```

## Remote access with Tailscale (recommended over port forwarding)
1. Install Tailscale on the Mac and your iPhone/iPad/PC; sign in to the same tailnet.
2. Open `http://<mac-tailscale-ip>:8765` (the launcher prints it). Tailscale addresses (100.64.0.0/10) are allowed by the app.
3. For HTTPS: `tailscale serve --bg 8765` then set `EXECHUB_COOKIE_SECURE=true` in `.env` and use the `https://<mac>.<tailnet>.ts.net` URL.
**Never** port-forward 8765 on your router; the app also rejects public-internet client addresses.

## Moving to a VPS / PostgreSQL later
1. `pip install "psycopg[binary]"` in the venv.
2. Set `EXECHUB_DATABASE_URL=postgresql+psycopg://user:pass@host/executive_hub`; run `python -m app.cli init` (Alembic creates the schema).
3. Copy data: export from SQLite with your preferred tool (e.g. `pgloader data/executive_hub.db postgresql://…`).
4. Run `python -m app.server` under systemd; put it behind Tailscale (keep `EXECHUB_HOST` on the tailnet interface). Use `pg_dump` for backups (built-in backup is SQLite-only).

## Costs (target ≈ $100/month)
* Infrastructure: $0 (runs on the Mac). Data sources used by default are free.
* AI: optional; defaults to $3/day and $60/month hard limits, per-job $0.50, 120 requests/hour, response caching. Bulk extraction routes to `claude-haiku-5-5`; analysis/briefings to `claude-opus-5-5` (change routes in Settings).
* Costs are computed from provider-reported token counts × list prices in `backend/app/ai/pricing.py`; add `ai_pricing_overrides` for OpenAI or new models (unknown models are costed conservatively at $10/$50 per M tokens).
