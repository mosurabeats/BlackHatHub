"""SAM.gov Get Opportunities Public API v2 adapter.

Requires a free SAM.gov API key (env SAM_GOV_API_KEY). Without a key the
source is marked ``needs_credentials`` and the run records that limitation.
Implemented against the published API contract; covered by mocked tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ...config import get_settings
from ...models import Source
from ..base import Candidate, CredentialsMissing, FetchResult, RawRecord, register
from ..normalize import clean_text, parse_date

API = "https://api.sam.gov/opportunities/v2/search"


@register
class SamGovOpportunitiesAdapter:
    name = "samgov_opportunities"
    requires = ["SAM_GOV_API_KEY"]

    def fetch(self, source: Source, http, max_records: int) -> FetchResult:
        key = get_settings().sam_gov_api_key
        if not key:
            raise CredentialsMissing("SAM_GOV_API_KEY (free key from sam.gov account settings)")
        cfg = source.config
        now = datetime.now(timezone.utc)
        params = {
            "api_key": key,
            "postedFrom": (now - timedelta(days=int(cfg.get("posted_days", 14)))).strftime("%m/%d/%Y"),
            "postedTo": now.strftime("%m/%d/%Y"),
            "limit": min(max_records, 1000),
            "offset": 0,
        }
        if cfg.get("naics"):
            params["ncode"] = cfg["naics"][0]
        if cfg.get("ptype"):
            params["ptype"] = cfg["ptype"]
        if cfg.get("state"):
            params["state"] = cfg["state"]
        resp = http.get(API, params=params, rate_per_minute=min(source.rate_limit_per_minute, 10))
        data = resp.json()
        records = []
        for row in data.get("opportunitiesData", []) or []:
            nid = row.get("noticeId")
            if nid:
                records.append(RawRecord(external_id=nid, data=row, url=row.get("uiLink") or f"https://sam.gov/opp/{nid}/view", retrieved_at=now))
        # Never log the API key.
        return FetchResult(records=records, request_urls=[API + " (key redacted)"])

    def extract(self, source: Source, record: RawRecord) -> Candidate | None:
        d = record.data
        pop = d.get("placeOfPerformance") or {}
        state = ((pop.get("state") or {}).get("code")) if isinstance(pop, dict) else None
        award = d.get("award") or {}
        return Candidate(
            external_key=f"{source.key}:{record.external_id}",
            title=clean_text(d.get("title"), 300) or "SAM.gov opportunity",
            summary=(
                f"{d.get('type', 'Notice')} posted {d.get('postedDate', 'n/a')} by {clean_text(d.get('fullParentPathName'), 200)}. "
                f"Solicitation {d.get('solicitationNumber') or 'n/a'}; responses due {d.get('responseDeadLine') or 'n/a'}."
            ),
            entity_name=clean_text(d.get("fullParentPathName"), 200) or None,
            category="solicitation",
            jurisdiction_code=state,
            location=state,
            reported_value=float(award["amount"]) if isinstance(award, dict) and award.get("amount") else None,
            source_url=record.url,
            deadline=parse_date(d.get("responseDeadLine")),
            data={k: d.get(k) for k in ("noticeId", "solicitationNumber", "type", "naicsCode", "setAside", "postedDate", "responseDeadLine", "typeOfSetAsideDescription")},
            excerpt=clean_text(d.get("description"), 600),
        )
