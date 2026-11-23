"""USAspending.gov contract-award adapter (free, no API key).

Finds federal contract awards whose period of performance ends within a
configurable window -- i.e. likely renewal / recompete (rebid) opportunities.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ...models import Source
from ..base import Candidate, FetchResult, RawRecord, register
from ..normalize import clean_text, parse_date

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
FIELDS = [
    "Award ID", "Recipient Name", "Award Amount", "Awarding Agency", "Awarding Sub Agency",
    "Start Date", "End Date", "Description", "NAICS", "Place of Performance State Code", "generated_internal_id",
]


@register
class USAspendingAwardsAdapter:
    name = "usaspending_awards"

    def fetch(self, source: Source, http, max_records: int) -> FetchResult:
        cfg = source.config
        now = datetime.now(timezone.utc)
        lookback = int(cfg.get("action_lookback_days", 730))
        filters: dict = {
            "award_type_codes": cfg.get("award_type_codes", ["A", "B", "C", "D"]),
            "time_period": [{"start_date": (now - timedelta(days=lookback)).date().isoformat(), "end_date": now.date().isoformat()}],
        }
        if cfg.get("naics"):
            filters["naics_codes"] = {"require": cfg["naics"]}
        if cfg.get("keywords"):
            filters["keywords"] = cfg["keywords"]
        if cfg.get("states"):
            filters["place_of_performance_locations"] = [{"country": "USA", "state": s} for s in cfg["states"]]
        min_end = now + timedelta(days=int(cfg.get("ends_after_days", 60)))
        max_end = now + timedelta(days=int(cfg.get("ends_before_days", 540)))
        records: list[RawRecord] = []
        urls: list[str] = []
        page = 1
        while len(records) < max_records and page <= int(cfg.get("max_pages", 5)):
            body = {"filters": filters, "fields": FIELDS, "limit": 100, "page": page, "sort": "Award Amount", "order": "desc"}
            resp = http.post_json(API, body, rate_per_minute=source.rate_limit_per_minute)
            urls.append(f"{API} (page {page})")
            data = resp.json()
            for row in data.get("results", []):
                end = parse_date(row.get("End Date"))
                if not end or not (min_end <= end <= max_end):
                    continue
                gid = row.get("generated_internal_id") or row.get("Award ID")
                records.append(RawRecord(external_id=str(gid), data=row, url=f"https://www.usaspending.gov/award/{gid}", retrieved_at=now))
            if not data.get("page_metadata", {}).get("hasNext"):
                break
            page += 1
        return FetchResult(records=records[:max_records], request_urls=urls)

    def extract(self, source: Source, record: RawRecord) -> Candidate | None:
        d = record.data
        end = parse_date(d.get("End Date"))
        amount = d.get("Award Amount")
        naics = d.get("NAICS") or {}
        agency = clean_text(d.get("Awarding Sub Agency") or d.get("Awarding Agency"))
        recipient = clean_text(d.get("Recipient Name"))
        return Candidate(
            external_key=f"{source.key}:{record.external_id}",
            title=f"Recompete window: {agency} - {clean_text(d.get('Description'), 120) or d.get('Award ID')}",
            summary=(
                f"Federal contract {d.get('Award ID')} held by {recipient} (obligated ${float(amount or 0):,.0f}) ends "
                f"{end.date().isoformat() if end else 'n/a'}. Expiring awards are often re-competed or renewed; "
                "this is a signal to monitor SAM.gov for the follow-on solicitation, not a confirmed solicitation."
            ),
            entity_name=agency,
            category="contract_recompete",
            jurisdiction_code=d.get("Place of Performance State Code"),
            location=d.get("Place of Performance State Code"),
            reported_value=float(amount) if amount is not None else None,
            source_url=record.url,
            deadline=end,
            data={"award_id": d.get("Award ID"), "incumbent": recipient, "naics": naics, "agency": agency,
                  "start_date": d.get("Start Date"), "end_date": d.get("End Date")},
            excerpt=clean_text(d.get("Description"), 600),
        )
