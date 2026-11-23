"""Socrata Open Data (SODA) adapter -- many official government portals.

Supports three extraction profiles:
* ``unclaimed_property`` -- municipal/state unclaimed property lists
* ``building_permit``   -- building permit datasets
* ``warn_notice``       -- WARN (layoff/closure) notices

Config keys::

    domain, dataset, profile, jurisdiction, holder (unclaimed property),
    fields: {owner|entity, amount|value, address, city, date, title_fields, contacts_prefix}
    where (SoQL), order, corporate_only (bool), owner_keyword_filter (bool),
    since_days + date_field (incremental window), page_size
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ...config import get_settings
from ...models import Source
from ..base import Candidate, ContactInfo, FetchResult, RawRecord, register
from ..normalize import clean_text, looks_corporate, parse_date, parse_money

CORP_KEYWORDS = ["LLC", "INC", "CORP", "COMPANY", "LTD", "LLP", "HOLDINGS", "PROPERTIES", "PARTNERS", "BANK", "ENTERPRISES", "ASSOCIATES", "MANAGEMENT", "APARTMENTS", "SERVICES", "GROUP", " LP"]


def _field(rec: dict[str, Any], spec: Any) -> str:
    if not spec:
        return ""
    if isinstance(spec, list):
        return clean_text(" ".join(clean_text(rec.get(f)) for f in spec if rec.get(f)))
    v = rec.get(spec)
    if isinstance(v, dict):  # e.g. Socrata URL / location objects
        v = v.get("url") or v.get("human_address") or ""
    return clean_text(v)


@register
class SocrataDatasetAdapter:
    name = "socrata_dataset"

    def _base(self, cfg: dict[str, Any]) -> str:
        return f"https://{cfg['domain']}/resource/{cfg['dataset']}.json"

    def build_where(self, cfg: dict[str, Any], now: datetime | None = None) -> str | None:
        clauses: list[str] = []
        if cfg.get("where"):
            clauses.append(f"({cfg['where']})")
        fields = cfg.get("fields", {})
        owner_field = fields.get("filter_field") or fields.get("owner") or fields.get("entity")
        if cfg.get("owner_keyword_filter") and isinstance(owner_field, str):
            ors = " OR ".join(f"upper({owner_field}) like '%{k.strip()}%'" for k in CORP_KEYWORDS)
            clauses.append(f"({ors})")
        if cfg.get("since_days") and fields.get("date"):
            since = (now or datetime.now(timezone.utc)) - timedelta(days=int(cfg["since_days"]))
            clauses.append(f"{fields['date']} >= '{since.strftime('%Y-%m-%dT00:00:00')}'")
        return " AND ".join(clauses) or None

    def fetch(self, source: Source, http, max_records: int) -> FetchResult:
        cfg = source.config
        url = self._base(cfg)
        page_size = min(int(cfg.get("page_size", 500)), max_records)
        offset = int((source.cursor or {}).get("offset", 0)) if not cfg.get("since_days") else 0
        where = self.build_where(cfg)
        headers = {}
        token = get_settings().socrata_app_token
        if token:
            headers["X-App-Token"] = token
        records: list[RawRecord] = []
        urls: list[str] = []
        exhausted = False
        while len(records) < max_records:
            params: dict[str, Any] = {
                "$select": "*, :id",
                "$limit": page_size,
                "$offset": offset,
                "$order": cfg.get("order", ":id"),
            }
            if where:
                params["$where"] = where
            resp = http.get(url, params=params, headers=headers, rate_per_minute=source.rate_limit_per_minute)
            urls.append(resp.url)
            rows = resp.json()
            if not isinstance(rows, list):
                break
            now = datetime.now(timezone.utc)
            for row in rows:
                rid = str(row.get(":id") or "")
                if not rid:
                    continue
                records.append(
                    RawRecord(
                        external_id=rid,
                        data=row,
                        url=f"https://{cfg['domain']}/resource/{cfg['dataset']}.json?$where=:id='{rid}'",
                        retrieved_at=now,
                    )
                )
            offset += len(rows)
            if len(rows) < page_size:
                exhausted = True
                break
        cursor = {"offset": 0 if exhausted else offset, "last_full_pass_complete": exhausted}
        return FetchResult(records=records[:max_records], request_urls=urls, new_cursor=cursor, truncated=not exhausted)

    def presence_check(self, source: Source, http, external_id: str) -> dict[str, Any] | None:
        """Re-query the authoritative source for one record (verification)."""
        cfg = source.config
        resp = http.get(
            self._base(cfg),
            params={"$select": "*, :id", "$where": f":id='{external_id}'"},
            rate_per_minute=source.rate_limit_per_minute,
            use_cache=False,
        )
        rows = resp.json()
        return rows[0] if rows else None

    # ------------------------------------------------------------------ extract
    def extract(self, source: Source, record: RawRecord) -> Candidate | None:
        profile = source.config.get("profile", "unclaimed_property")
        fn = getattr(self, f"_extract_{profile}")
        return fn(source, record)

    def _common(self, source: Source, record: RawRecord) -> dict[str, Any]:
        cfg = source.config
        return {
            "external_key": f"{source.key}:{record.external_id}",
            "jurisdiction_code": cfg.get("jurisdiction"),
            "source_url": record.url,
            "data": {k: v for k, v in record.data.items() if not str(k).startswith(":@")},
        }

    def _extract_unclaimed_property(self, source: Source, record: RawRecord) -> Candidate | None:
        cfg = source.config
        f = cfg.get("fields", {})
        owner = _field(record.data, f.get("owner"))
        if not owner:
            return None
        if cfg.get("corporate_only", True) and not looks_corporate(owner):
            return None  # individuals are out of scope (corporate recovery only)
        amount = parse_money(record.data.get(f.get("amount"))) if f.get("amount") else None
        address = _field(record.data, f.get("address"))
        city = _field(record.data, f.get("city"))
        holder = cfg.get("holder", source.name)
        date = parse_date(record.data.get(f.get("date"))) if f.get("date") else None
        amt_txt = f"${amount:,.2f}" if amount is not None else "amount not published"
        summary = (
            f"Public unclaimed-property listing published by {holder} names '{owner}' as owner "
            f"({amt_txt}). Listing date: {date.date().isoformat() if date else 'not published'}."
        )
        return Candidate(
            title=f"{owner} - unclaimed property held by {holder}",
            summary=summary,
            entity_name=owner,
            category="unclaimed_property",
            location=", ".join(x for x in [address, city] if x) or None,
            reported_value=amount,
            excerpt=clean_text(record.data, 600),
            **self._common(source, record),
        )

    def _extract_building_permit(self, source: Source, record: RawRecord) -> Candidate | None:
        cfg = source.config
        f = cfg.get("fields", {})
        d = record.data
        address = _field(d, f.get("address"))
        work = _field(d, f.get("work_type")) or "Permit"
        desc = _field(d, f.get("description"))
        value = parse_money(d.get(f.get("value"))) if f.get("value") else None
        min_value = cfg.get("min_value")
        if min_value and (value is None or value < float(min_value)):
            return None
        contacts: list[ContactInfo] = []
        prefix = f.get("contacts_prefix")
        if prefix:
            for i in range(1, 16):
                nm = clean_text(d.get(f"{prefix}{i}_name"))
                if nm:
                    contacts.append(ContactInfo(name=nm, role=clean_text(d.get(f"{prefix}{i}_type")) or None, organization=None))
        contractor = _field(d, f.get("contractor"))
        if contractor:
            contacts.append(ContactInfo(name=contractor, role="Contractor (public record)"))
        entity = contractor or next((c.name for c in contacts if c.role and "CONTRACTOR" in c.role.upper()), None) or (contacts[0].name if contacts else None)
        issued = parse_date(d.get(f.get("date"))) if f.get("date") else None
        val_txt = f"${value:,.0f}" if value is not None else "not reported"
        return Candidate(
            title=f"{work}: {address or 'address not published'}",
            summary=f"{desc[:400]} Reported project cost: {val_txt}. Issued: {issued.date().isoformat() if issued else 'n/a'}.",
            entity_name=entity,
            category="building_permit",
            location=address or None,
            reported_value=value,
            contacts=contacts,
            excerpt=desc[:600],
            **self._common(source, record),
        )

    def _extract_warn_notice(self, source: Source, record: RawRecord) -> Candidate | None:
        f = source.config.get("fields", {})
        d = record.data
        company = _field(d, f.get("entity"))
        if not company:
            return None
        city = _field(d, f.get("city"))
        layoffs = parse_money(d.get(f.get("count"))) if f.get("count") else None
        layoff_date = parse_date(d.get(f.get("deadline"))) if f.get("deadline") else None
        notice_date = parse_date(d.get(f.get("date"))) if f.get("date") else None
        return Candidate(
            title=f"WARN notice: {company} ({city or 'location n/a'})",
            summary=(
                f"Official WARN notice filed {notice_date.date().isoformat() if notice_date else 'n/a'} reports "
                f"{int(layoffs) if layoffs else 'an unspecified number of'} affected workers at {company}, "
                f"effective {layoff_date.date().isoformat() if layoff_date else 'n/a'}. A WARN notice indicates "
                "a closure or mass layoff; it does NOT establish that equipment is for sale."
            ),
            entity_name=company,
            category="closure_signal",
            location=city or None,
            reported_value=None,
            deadline=layoff_date,
            excerpt=clean_text(d, 600),
            data={**self._common(source, record)["data"], "affected_workers": layoffs},
            **{k: v for k, v in self._common(source, record).items() if k != "data"},
        )
