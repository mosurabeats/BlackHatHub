# Known limitations and remaining integrations

This list is deliberately explicit. Nothing here is presented elsewhere as done.

## Legal / compliance content
* **No state's finder rules have been researched or verified.** All 51 jurisdictions start as `unverified_seed`
  with legal fields marked "Needs research". This is intentional: the system will not assert licensing, fee
  caps, waiting periods or contract rules that a person has not confirmed from the statute or agency. Asset-recovery
  outreach approvals remain blocked until you verify and clear each state you intend to operate in.
* Seeded agency names/URLs came from general knowledge. A live check (Nov 2026) found 38/51 reachable, 7 that refuse
  automated requests (403 — likely fine in a browser), and 6 wrong URLs that were corrected (DC, HI, MN, NJ, OH, LA).
  Re-check periodically; the weekly job flags changes and failures.
* Compliance rules are heuristics that *flag* issues; they are not legal advice. Consult counsel before operating.

## Data coverage
* **Statewide unclaimed-property data is not integrated.** State portals are interactive name searches (often with
  CAPTCHA and terms that prohibit automated querying). Integrated sources are municipal open-data lists (Austin TX,
  College Station TX, Providence RI, Montgomery County MD) plus any you enable from discovery proposals.
  *Path:* California SCO publishes bulk files, but the download page returned 403 to this environment; add a
  `csv_bulk` adapter (stream-parse, filter corporate owners ≥ threshold) once access is confirmed. Some states sell or
  license holder files to registered finders — purchasing data requires an approval (`purchase_dataset`).
* The Austin dataset publishes names only (no amounts), so those records stay low-priority until values are confirmed.
* **Entity verification** exists only for Texas (Comptroller franchise-tax open data). *Path:* add verifiers for other
  states' Secretary of State open datasets (e.g. NY, CO, OR on Socrata) or OpenCorporates (paid API key).
* **Liquidation:** only Texas WARN notices. Not integrated: GSA Auctions API (needs api.data.gov key), other states'
  WARN data (mostly PDFs/HTML), bankruptcy filings (PACER is paid; CourtListener API is a candidate), commercial auction sites.
* **Procurement:** USAspending (recompete windows) works keylessly; SAM.gov needs `SAM_GOV_API_KEY` and was tested only
  against mocked responses built from the published API contract. State and municipal procurement portals are not
  integrated (hundreds of heterogeneous systems); add RSS feeds or Socrata datasets where agencies publish them.
* Default procurement scoring favours large contracts; set the NAICS codes in the source config to match your capability.
* **Private ventures (04-06):** workspace, CRM, tasks, financials, compliance notes and RSS market-intelligence
  plumbing are implemented. The seeded news feeds are *proposed/disabled* (aggregator feeds — review their terms first).
  No content generation, platform integrations or venture-specific data sources are included.

## Execution & integrations
* **No outbound executors** (email, mail, e-filing, payments, account creation). Approvals authorize a specific action;
  you perform it and record the result. `pipeline.assert_authorized()` is the required gate for any future executor.
* Notifications are in-app only (no push/email/SMS).
* **AI was not called live during development** (no API key in the build environment). The AI gateway, budgets,
  caching and injection isolation are tested with a fake provider. The Opus/Sonnet routes use Anthropic's
  server-side refusal-fallback beta (`fallbacks="default"`); if your account rejects that beta, set routes to
  `claude-haiku-5-5` or remove the beta call in `ai/client.py`. OpenAI prices must be entered as overrides.

## Platform
* `START-MAC.command` was exercised on Linux with stand-ins for macOS commands (`caffeinate`, `open`, `ipconfig`);
  it has not run on a physical Mac. `START-WINDOWS.bat` was not executed.
* Scheduled research runs only while the hub is running and the Mac is awake (the launcher prevents idle sleep;
  closing the lid still sleeps). Missed runs are caught up once on restart.
* Single owner account; no multi-user roles.
* Rate limiting is in-process (fine for a single host; use a shared store if you ever run multiple instances).
* PostgreSQL support is by design (portable types, Alembic) but was not exercised against a live PostgreSQL server.
* Search uses SQL `LIKE` (adequate for tens of thousands of records).
* Frontend has no automated UI test suite; it was verified by building, type-checking and browser screenshots.
