"""Monitoring: stale-lead detection, re-verification, requalification, portal checks, source discovery."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..app_settings import all_settings
from ..audit import audit
from ..models import Business, Evidence, Jurisdiction, Opportunity, Source
from ..pipeline import record_history, transition
from ..research.base import AdapterError, get_adapter
from ..research.engine import evaluate

ACTIVE_INTERNAL = ("discovered", "researching", "verified", "qualified")


def detect_stale(db: Session, business: Business) -> int:
    days = int(all_settings(db)["stale_after_days"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    n = 0
    for opp in db.execute(select(Opportunity).where(Opportunity.business_id == business.id,
                                                    Opportunity.stage.in_(ACTIVE_INTERNAL),
                                                    Opportunity.is_stale.is_(False),
                                                    Opportunity.last_seen_at < cutoff)).scalars():
        opp.is_stale = True
        record_history(db, opp, "note", "agent:pipeline_manager", f"Marked stale: not seen in source for {days}+ days")
        n += 1
    return n


def requalify(db: Session, business: Business) -> int:
    settings = all_settings(db)
    n = 0
    for opp in db.execute(select(Opportunity).where(Opportunity.business_id == business.id,
                                                    Opportunity.stage.in_(ACTIVE_INTERNAL))).scalars():
        jur = db.get(Jurisdiction, opp.jurisdiction_code) if opp.jurisdiction_code else None
        evaluate(db, opp, business, jur, settings, actor="agent:opportunity_analyst")
        n += 1
    return n


def reverify(db: Session, business: Business, http, limit: int = 25) -> dict[str, int]:
    """Re-check that source records still exist at the official publisher."""
    out = {"checked": 0, "confirmed": 0, "missing": 0, "errors": 0}
    opps = db.execute(select(Opportunity).where(Opportunity.business_id == business.id,
                                                Opportunity.stage.in_(ACTIVE_INTERNAL + ("awaiting_approval",)))
                      .order_by(Opportunity.last_verified_at.asc().nullsfirst()).limit(limit)).scalars().all()
    for opp in opps:
        src = db.get(Source, opp.source_id) if opp.source_id else None
        if not src or src.adapter != "socrata_dataset":
            continue
        adapter = get_adapter(src.adapter)
        rid = (opp.data or {}).get("records", [None])[0]
        if not rid:
            continue
        out["checked"] += 1
        try:
            row = adapter.presence_check(src, http, rid)
        except AdapterError:
            out["errors"] += 1
            continue
        now = datetime.now(timezone.utc)
        if row is not None:
            opp.last_verified_at = now
            out["confirmed"] += 1
            db.add(Evidence(opportunity_id=opp.id, source_id=src.id, kind="verification",
                            title="Re-verified: record still published at official source", url=opp.source_url,
                            excerpt=f"Record {rid} present on {now.date().isoformat()}", supports_verification=True))
        else:
            out["missing"] += 1
            db.add(Evidence(opportunity_id=opp.id, source_id=src.id, kind="verification",
                            title="Record no longer published at source", url=opp.source_url,
                            excerpt=f"Record {rid} absent on {now.date().isoformat()} (possibly claimed or removed)"))
            if opp.stage in ACTIVE_INTERNAL:
                transition(db, opp, "lost", "agent:research_analyst",
                           "Record no longer listed at the official source (possibly claimed or removed)")
    return out


def check_jurisdiction_portals(db: Session, http, limit: int | None = None) -> dict[str, int]:
    out = {"checked": 0, "reachable": 0, "unreachable": 0, "changed": 0}
    jurs = db.execute(select(Jurisdiction).order_by(Jurisdiction.portal_last_checked_at.asc().nullsfirst())).scalars().all()
    for jur in jurs[: limit or len(jurs)]:
        url = jur.agency_url or jur.search_portal_url
        if not url:
            continue
        out["checked"] += 1
        now = datetime.now(timezone.utc)
        jur.portal_last_checked_at = now
        try:
            resp = http.get(url, rate_per_minute=20, retries=1, use_cache=False, accept_statuses=(200,))
            # Hash visible text only (strip scripts/tags) so cosmetic token changes don't count.
            text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", resp.text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            import hashlib

            h = hashlib.sha256(text.encode()).hexdigest()
            if jur.portal_content_hash and jur.portal_content_hash != h:
                jur.portal_changed_at = now
                out["changed"] += 1
            jur.portal_content_hash = h
            jur.portal_status = "reachable"
            jur.portal_http_status = resp.status
            out["reachable"] += 1
        except AdapterError as exc:
            jur.portal_status = "blocked" if "refused" in exc.limitation else "unreachable"
            m = re.search(r"\((\d{3})\)|HTTP (\d{3})", str(exc))
            jur.portal_http_status = int(next(g for g in m.groups() if g)) if m else None
            out["unreachable"] += 1
    audit(db, "agent:compliance_analyst", "jurisdictions.portal_check", detail=out)
    return out


def discover_sources(db: Session, discovery_source: Source, http) -> int:
    """Source Discovery Agent: propose (never auto-enable) new official datasets."""
    adapter = get_adapter(discovery_source.adapter)
    proposals = adapter.discover(discovery_source, http)
    n = 0
    for p in proposals:
        if db.execute(select(Source.id).where(Source.key == p.key)).first():
            continue
        if db.execute(select(Source.id).where(Source.config["dataset"].as_string() == p.config.get("dataset"))).first():
            continue
        db.add(Source(key=p.key, business_id=discovery_source.business_id, name=p.name[:255], adapter=p.adapter,
                      config=p.config, url=p.url, official=True, enabled=False, status="proposed",
                      discovered_by="agent:source_discovery", access_notes=p.notes))
        n += 1
    discovery_source.last_run_at = datetime.now(timezone.utc)
    discovery_source.last_success_at = discovery_source.last_run_at
    audit(db, "agent:source_discovery", "sources.discovered", business_id=discovery_source.business_id, detail={"proposed": n})
    return n
