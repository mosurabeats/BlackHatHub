"""Idempotent seeding of businesses, vault, jurisdictions, sources and schedules.

No opportunities, revenue or contacts are seeded: all pipeline data must come
from research runs or the owner.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .jurisdictions_data import JURISDICTIONS, MISSING_MONEY, NAUPA_DIRECTORY, NEEDS_RESEARCH
from .models import Business, Jurisdiction, Schedule, Source, VaultConfig
from .security import hash_secret

BUSINESSES = [
    dict(code="B07", slug="asset-recovery", name="Nationwide Corporate Asset Recovery", priority=1, sort_order=1,
         qualify_threshold=55, reject_threshold=20,
         description="Identifies lawful corporate unclaimed-property recovery opportunities across all 50 states and DC. "
                     "Highest-priority research engine. No claimant contact, claim filing, contracts or fees without approval and verified compliance."),
    dict(code="B01", slug="permit-intelligence", name="Commercial Permit Intelligence", priority=2, sort_order=2,
         qualify_threshold=72, reject_threshold=15,
         description="Discovers commercial building permits, developments, renovations and expansions; enriches and qualifies leads."),
    dict(code="B02", slug="liquidation-brokerage", name="Commercial Liquidation Brokerage", priority=3, sort_order=3,
         qualify_threshold=60, reject_threshold=15,
         description="Identifies businesses with equipment/assets potentially available for resale or liquidation (closures, relocations, surplus)."),
    dict(code="B03", slug="procurement-intelligence", name="Government Procurement Intelligence", priority=3, sort_order=4,
         qualify_threshold=75, reject_threshold=15,
         description="Monitors federal/state/municipal procurement, contract awards, renewals and rebid opportunities."),
    dict(code="B04", slug="ai-creator-studio", name="AI Adult Creator Studio", priority=5, sort_order=5, is_private=True,
         qualify_threshold=65, reject_threshold=15,
         description="Private: lawful adult-oriented business using fictional, adult (18+) AI-generated characters. Research, content planning, "
                     "operations, market intelligence and financial analysis. Never exploitative, nonconsensual or underage material."),
    dict(code="B05", slug="creator-ops-saas", name="Adult Creator Operations SaaS", priority=5, sort_order=6, is_private=True,
         qualify_threshold=65, reject_threshold=15,
         description="Private: software business serving adult-content creators - creator workflows, competitors, pricing, acquisition channels."),
    dict(code="B06", slug="niche-content-studio", name="Niche Adult Content Studio", priority=5, sort_order=7, is_private=True,
         qualify_threshold=65, reject_threshold=15,
         description="Private: lawful adult-content business research and operations - market intelligence, production planning, publishing, finance."),
]


def _gnews(q: str) -> str:
    from urllib.parse import quote

    return f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"


SOURCES = [
    # ---- B07 Nationwide Asset Recovery --------------------------------------
    dict(key="b07.austin_unclaimed", business="B07", name="City of Austin, TX - Unclaimed Property (open data)",
         adapter="socrata_dataset", official=True, jurisdiction_code="TX", url="https://datahub.austintexas.gov/d/h3i4-5e5v",
         config=dict(domain="datahub.austintexas.gov", dataset="h3i4-5e5v", profile="unclaimed_property", jurisdiction="TX",
                     holder="City of Austin", holder_type="municipal", fields={"owner": ["first", "last"], "filter_field": "last"},
                     owner_keyword_filter=True, corporate_only=True, dedupe="entity", entity_verifier="texas_franchise_tax"),
         access_notes="City-held unclaimed property list (Texas Property Code ch. 76). Amounts are not published in this dataset."),
    dict(key="b07.college_station_unclaimed", business="B07", name="City of College Station, TX - Unclaimed Property (open data)",
         adapter="socrata_dataset", official=True, jurisdiction_code="TX", url="https://data.cstx.gov/d/q83i-2ks8",
         config=dict(domain="data.cstx.gov", dataset="q83i-2ks8", profile="unclaimed_property", jurisdiction="TX",
                     holder="City of College Station", holder_type="municipal",
                     fields={"owner": ["first_name", "last_name"], "filter_field": "last_name", "amount": "amount", "address": "address"},
                     owner_keyword_filter=True, corporate_only=True, dedupe="entity", entity_verifier="texas_franchise_tax"),
         access_notes="City-held unclaimed property with published amounts."),
    dict(key="b07.providence_unclaimed", business="B07", name="City of Providence, RI - Uncashed Checks / Unclaimed Property",
         adapter="socrata_dataset", official=True, jurisdiction_code="RI", url="https://data.providenceri.gov/d/4hhd-fzq6",
         config=dict(domain="data.providenceri.gov", dataset="4hhd-fzq6", profile="unclaimed_property", jurisdiction="RI",
                     holder="City of Providence", holder_type="municipal",
                     fields={"owner": "payee_name", "amount": "payment_amount", "address": "payee_address1", "city": "city", "date": "check_date"},
                     owner_keyword_filter=True, corporate_only=True, dedupe="entity"),
         access_notes="Checks issued by the City of Providence not cashed after one year."),
    dict(key="b07.montgomery_md_unclaimed", business="B07", name="Montgomery County, MD - Unclaimed Payments Over 3 Years Old",
         adapter="socrata_dataset", official=True, jurisdiction_code="MD", url="https://data.montgomerycountymd.gov/d/vfcf-uhd9",
         config=dict(domain="data.montgomerycountymd.gov", dataset="vfcf-uhd9", profile="unclaimed_property", jurisdiction="MD",
                     holder="Montgomery County, MD", holder_type="municipal",
                     fields={"owner": "vendor", "amount": "amount", "date": "payment_date"}, corporate_only=True, dedupe="entity")),
    dict(key="b07.discovery", business="B07", name="Source Discovery - Socrata catalog (unclaimed property datasets)",
         adapter="socrata_catalog", official=True, url="https://api.us.socrata.com/api/catalog/v1",
         config=dict(queries=["unclaimed property", "unclaimed funds", "uncashed checks", "outstanding checks"],
                     name_must_include=["unclaimed", "uncashed", "outstanding check"], profile="unclaimed_property")),
    # ---- B01 Commercial Permits -------------------------------------------------
    dict(key="b01.chicago_permits", business="B01", name="City of Chicago - Building Permits (>$250k)", adapter="socrata_dataset",
         official=True, jurisdiction_code="IL", url="https://data.cityofchicago.org/d/ydr8-5enu",
         config=dict(domain="data.cityofchicago.org", dataset="ydr8-5enu", profile="building_permit", jurisdiction="IL",
                     where="reported_cost > 250000", order="issue_date DESC", since_days=21, min_value=250000,
                     fields={"address": ["street_number", "street_direction", "street_name"], "work_type": "permit_type",
                             "description": "work_description", "value": "reported_cost", "date": "issue_date", "contacts_prefix": "contact_"})),
    dict(key="b01.seattle_permits", business="B01", name="City of Seattle - Non-Residential Building Permits", adapter="socrata_dataset",
         official=True, jurisdiction_code="WA", url="https://cos-data.seattle.gov/d/76t5-zqzr",
         config=dict(domain="cos-data.seattle.gov", dataset="76t5-zqzr", profile="building_permit", jurisdiction="WA",
                     where="permitclassmapped = 'Non-Residential' AND estprojectcost > 100000", order="applieddate DESC",
                     since_days=45, min_value=100000,
                     fields={"address": "originaladdress1", "work_type": "permittypedesc", "description": "description",
                             "value": "estprojectcost", "date": "applieddate", "contractor": "contractorcompanyname"})),
    dict(key="b01.discovery", business="B01", name="Source Discovery - Socrata catalog (building permits)", adapter="socrata_catalog",
         official=True, config=dict(queries=["building permits", "commercial permits"], name_must_include=["permit"], profile="building_permit")),
    # ---- B02 Liquidation ---------------------------------------------------------
    dict(key="b02.texas_warn", business="B02", name="Texas Workforce Commission - WARN Notices", adapter="socrata_dataset",
         official=True, jurisdiction_code="TX", url="https://data.texas.gov/d/8w53-c4f6",
         config=dict(domain="data.texas.gov", dataset="8w53-c4f6", profile="warn_notice", jurisdiction="TX", order="notice_date DESC",
                     since_days=180, fields={"entity": "job_site_name", "city": "city_name", "count": "total_layoff_number",
                                             "deadline": "layoff_date", "date": "notice_date"})),
    dict(key="b02.discovery", business="B02", name="Source Discovery - Socrata catalog (WARN / closures)", adapter="socrata_catalog",
         official=True, config=dict(queries=["WARN notices", "business closures", "surplus equipment auction"],
                                    name_must_include=["warn", "closure", "surplus", "auction"], profile="warn_notice")),
    # ---- B03 Procurement ---------------------------------------------------------
    dict(key="b03.usaspending_recompete", business="B03", name="USAspending.gov - Expiring federal contracts (recompete window)",
         adapter="usaspending_awards", official=True, url="https://www.usaspending.gov/",
         config=dict(naics=["541611", "541512", "561720", "238220", "541330"], ends_after_days=60, ends_before_days=540, max_pages=3),
         access_notes="Free public API. NAICS list is configurable."),
    dict(key="b03.samgov_opportunities", business="B03", name="SAM.gov - Contract Opportunities", adapter="samgov_opportunities",
         official=True, url="https://sam.gov/", config=dict(posted_days=7, naics=["541611"]),
         access_notes="Requires free SAM.gov API key in SAM_GOV_API_KEY."),
    # ---- Private ventures (feeds proposed; owner reviews terms before enabling) ---------
    dict(key="b04.market_news", business="B04", name="Market news - AI companion / virtual creator industry (Google News RSS)",
         adapter="rss_feed", official=False, enabled=False, status="proposed", url=_gnews('"AI influencer" OR "virtual creator" OR "AI companion" market'),
         config=dict(url=_gnews('"AI influencer" OR "virtual creator" OR "AI companion" market'), category="market_signal"),
         access_notes="News aggregator feed (not an official source). Review provider terms before enabling."),
    dict(key="b05.market_news", business="B05", name="Market news - creator economy software (Google News RSS)", adapter="rss_feed",
         official=False, enabled=False, status="proposed", url=_gnews('"creator economy" software OR SaaS'),
         config=dict(url=_gnews('"creator economy" software OR SaaS'), category="market_signal"),
         access_notes="News aggregator feed (not an official source). Review provider terms before enabling."),
    dict(key="b06.market_news", business="B06", name="Market news - subscription content platforms (Google News RSS)", adapter="rss_feed",
         official=False, enabled=False, status="proposed", url=_gnews('"subscription platform" creators policy OR payouts'),
         config=dict(url=_gnews('"subscription platform" creators policy OR payouts'), category="market_signal"),
         access_notes="News aggregator feed (not an official source). Review provider terms before enabling."),
]

SCHEDULES = [
    dict(key="research_cycle", name="Research cycle (all enabled sources) + pipeline maintenance + briefing", job_type="research_cycle",
         interval_minutes=720),
    dict(key="jurisdiction_portal_check", name="Jurisdiction portal checks (51 jurisdictions)", job_type="jurisdiction_portal_check",
         interval_minutes=10080),
    dict(key="backup_daily", name="Daily database backup", job_type="backup", interval_minutes=1440),
]


def seed(db: Session) -> None:
    s = get_settings()
    by_code: dict[str, Business] = {}
    for spec in BUSINESSES:
        b = db.execute(select(Business).where(Business.code == spec["code"])).scalars().first()
        if b is None:
            b = Business(**spec)
            db.add(b)
        by_code[spec["code"]] = b
    db.flush()

    if db.get(VaultConfig, 1) is None:
        db.add(VaultConfig(id=1, pin_hash=hash_secret(s.initial_vault_pin), is_initial_pin=True))

    for code, name, agency, agency_url, portal in JURISDICTIONS:
        if db.get(Jurisdiction, code) is None:
            db.add(Jurisdiction(
                code=code, name=name, agency_name=agency, agency_url=agency_url, search_portal_url=portal,
                data_availability="Public name search portal (per seed); bulk/API availability not yet researched.",
                finder_registration=NEEDS_RESEARCH, fee_restrictions=NEEDS_RESEARCH, waiting_period=NEEDS_RESEARCH,
                claimant_authorization_rules=NEEDS_RESEARCH, contract_requirements=NEEDS_RESEARCH,
                documentation_requirements=NEEDS_RESEARCH, statutory_references=NEEDS_RESEARCH,
                source_citations=[{"title": "Seed: agency directory (unverified)", "url": agency_url},
                                  {"title": "NAUPA state directory (cross-check)", "url": NAUPA_DIRECTORY},
                                  {"title": "MissingMoney multi-state search", "url": MISSING_MONEY}],
            ))

    for spec in SOURCES:
        spec = dict(spec)
        bcode = spec.pop("business")
        if db.execute(select(Source.id).where(Source.key == spec["key"])).first():
            continue
        db.add(Source(business_id=by_code[bcode].id, **spec))
    db.flush()

    now = datetime.now(timezone.utc)
    for i, spec in enumerate(SCHEDULES):
        if db.execute(select(Schedule.id).where(Schedule.key == spec["key"])).first():
            continue
        db.add(Schedule(next_run_at=now + timedelta(minutes=2 + i), **spec))
    for src in db.execute(select(Source).where(Source.adapter == "socrata_catalog")).scalars():
        key = f"discovery:{src.key}"
        if not db.execute(select(Schedule.id).where(Schedule.key == key)).first():
            db.add(Schedule(key=key, name=f"Source discovery: {src.name}", job_type="source_discovery",
                            business_id=src.business_id, source_id=src.id, interval_minutes=10080,
                            next_run_at=now + timedelta(minutes=10)))
    for src in db.execute(select(Source).where(Source.adapter == "samgov_opportunities")).scalars():
        if not s.sam_gov_api_key:
            src.status = "needs_credentials"
        elif src.status == "needs_credentials":
            src.status = "active"  # key was added since last start
    db.flush()
