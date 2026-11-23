# Executive Hub

A private, local-first operating system for researching and running a portfolio of seven businesses.
It discovers opportunities from official public data, verifies and scores them, keeps evidence for every
claim, maintains the pipeline automatically, and asks for your approval before anything leaves the building.

* **Runs on your Mac** (FastAPI + SQLite + built-in scheduler); iPhone/iPad/Windows connect through the browser.
* **Real data only**: every opportunity links to the official record it came from, with retrieval and verification dates.
* **Private vault** for Businesses 04-06 (PIN `2653` initially — change it in Settings).
* **Approval-gated**: agents research and recommend; contacting anyone, filing, paying or signing needs a single-use approval.
* **Cost-controlled AI** (optional): budgets, caching and model routing; works fully without API keys.

## Install & start (macOS)

1. Install **Python 3.12 or newer** if you don't have it: <https://www.python.org/downloads/macos/>
   (or `brew install python@3.12`). Node.js is *not* needed — the web UI ships prebuilt.
2. Unzip `ExecutiveHub-1.0.0.zip` somewhere permanent, e.g. `~/ExecutiveHub`.
3. Double-click **`START-MAC.command`**.
   *First time only:* macOS may block it. Right-click → **Open** → **Open**. If it says it isn't executable, run
   `chmod +x ~/ExecutiveHub/START-MAC.command` in Terminal once.
4. The launcher installs dependencies into a private `.venv`, creates `.env`, migrates the database, starts the
   server and opens <http://localhost:8765>. Create your owner account (12+ character password).
5. Keep the Terminal window open; **Ctrl+C** stops it gracefully. Data lives in `./data` (backups in `./data/backups`).

Optional: `scripts/install-mac-autostart.sh` starts the hub at login and restarts it if it crashes
(`scripts/install-mac-autostart.sh remove` to undo). Scheduled research only runs while the Mac is awake;
missed runs are caught up once on the next start.

### iPhone / iPad
On the same Wi-Fi, open the address the launcher prints (e.g. `http://192.168.1.20:8765`). In Safari use
Share → **Add to Home Screen** for an app-like icon. For access away from home, see Tailscale in
[docs/OPERATIONS.md](docs/OPERATIONS.md). The app refuses connections from public-internet addresses.

### Windows
Install Python 3.12+ (tick *Add python.exe to PATH*), then double-click **`START-WINDOWS.bat`**.

### Optional configuration (`.env`)
| Key | Enables |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | AI analysis of unstructured sources and AI-written briefing summaries |
| `SAM_GOV_API_KEY` | SAM.gov contract opportunities (free key from your SAM.gov account) |
| `SOCRATA_APP_TOKEN` | Higher rate limits on open-data portals |

Restart the hub after editing `.env`.

## Documentation
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components, data model, research engine, agents, security model
* [docs/OPERATIONS.md](docs/OPERATIONS.md) — daily use, backups/restore, Tailscale, PostgreSQL/VPS migration, CLI
* [docs/FEATURES.md](docs/FEATURES.md) — implemented-feature checklist with test evidence
* [docs/LIMITATIONS.md](docs/LIMITATIONS.md) — known limitations and remaining integrations (read this)

## Development
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend && pytest -q                         # 68 tests, mocked sources
EXECHUB_RUN_INTEGRATION=1 pytest -m integration # real public endpoints
python -m app.server                            # API + UI on :8765
cd ../frontend && npm install && npm run dev    # hot-reload UI on :5173 (proxies /api)
scripts/package.sh                              # build UI, run tests, create dist-zip/ExecutiveHub-1.0.0.zip
```
