"""Research engine: Retrieve -> Parse/Extract -> Verify -> Deduplicate -> Score -> Qualify -> Insert -> Recommend.

Each stage writes a ResearchEvent so every run has a complete audit trail.
A run is marked ``succeeded`` only if retrieval and processing actually
completed; failures are recorded with the limitation that caused them.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents import compliance, scoring
from ..ai import client as ai
from ..ai.budget import BudgetExceeded
from ..app_settings import all_settings
from ..audit import audit
from ..models import (
    Business,
    Contact,
    Evidence,
    Jurisdiction,
    Opportunity,
    ResearchEvent,
    ResearchRun,
    Source,
    Task,
)
from ..pipeline import record_history, transition
from . import verifiers
from .base import AdapterError, Candidate, get_adapter
from .normalize import content_hash, fingerprint, normalize_entity

log = logging.getLogger(__name__)
AGENT = "agent:research_analyst"

# Categories where the next step is monitoring/research, not outreach to a counterparty.
MONITOR_ONLY_CATEGORIES = {"contract_recompete", "solicitation", "market_signal"}

TRACKED_FIELDS = ["reported_value", "title", "location", "deadline", "entity_name"]

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "relevance": {"type": "integer", "description": "0-100 commercial relevance to the business"},
        "entity_name": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "key_facts": {"type": "array", "items": {"type": "string"}},
        "suggested_next_step": {"type": "string"},
        "unsupported_or_uncertain": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["relevance", "entity_name", "summary", "key_facts", "suggested_next_step", "unsupported_or_uncertain"],
    "additionalProperties": False,
}


class JobCancelled(Exception):
    pass


def _event(db: Session, run: ResearchRun, stage: str, status: str, message: str, **data: Any) -> None:
    run.current_stage = stage
    db.add(ResearchEvent(run_id=run.id, stage=stage, status=status, message=message[:2000], data=data))
    db.flush()


def _dedupe_key(source: Source, cand: Candidate) -> str:
    if source.config.get("dedupe") == "entity" and cand.entity_name:
        return fingerprint(source.key, normalize_entity(cand.entity_name), cand.category or "")
    return fingerprint(cand.external_key)


def run_source(
    db: Session,
    source: Source,
    http,
    *,
    job_id: int | None = None,
    check_cancel: Callable[[], None] = lambda: None,
    max_records: int | None = None,
) -> ResearchRun:
    business = db.get(Business, source.business_id)
    settings = all_settings(db)
    max_records = max_records or int(settings["research_max_records_per_run"])
    run = ResearchRun(job_id=job_id, business_id=source.business_id, source_id=source.id, status="running", stats={})
    db.add(run)
    db.flush()
    stats: dict[str, Any] = {"retrieved": 0, "out_of_scope": 0, "new": 0, "updated": 0, "unchanged": 0,
                             "rejected": 0, "qualified": 0, "verified": 0, "ai_enriched": 0}
    source.last_run_at = datetime.now(timezone.utc)
    adapter = get_adapter(source.adapter)

    # ---- Retrieve -------------------------------------------------------
    try:
        fetched = adapter.fetch(source, http, max_records)
    except AdapterError as exc:
        run.status = "failed"
        run.error = str(exc)
        run.limitations = [exc.limitation]
        run.finished_at = datetime.now(timezone.utc)
        source.last_error = exc.limitation
        source.consecutive_failures += 1
        if not exc.retryable:
            source.status = "needs_credentials" if "credential" in str(exc).lower() else "failing"
        _event(db, run, "retrieve", "error", exc.limitation)
        audit(db, AGENT, "research.retrieve_failed", target_type="source", target_id=source.id,
              business_id=source.business_id, detail={"error": str(exc)})
        db.flush()
        raise
    stats["retrieved"] = len(fetched.records)
    run.limitations = list(fetched.limitations)
    if fetched.truncated:
        run.limitations.append(f"Retrieved first {len(fetched.records)} records this run; remaining records continue next run.")
    _event(db, run, "retrieve", "ok", f"Retrieved {len(fetched.records)} records", urls=fetched.request_urls[:10])
    check_cancel()

    # ---- Parse / Extract -----------------------------------------------------
    candidates: list[tuple[Candidate, Any]] = []
    for rec in fetched.records:
        cand = adapter.extract(source, rec)
        if cand is None:
            stats["out_of_scope"] += 1
            continue
        candidates.append((cand, rec))
    _event(db, run, "extract", "ok", f"Extracted {len(candidates)} candidates; {stats['out_of_scope']} out of scope "
           f"(e.g. individuals or below filters)", extractor="deterministic")

    # AI enrichment for unstructured adapters (Research Analyst), budget permitting.
    if getattr(adapter, "unstructured", False) and candidates:
        provider, _model = ai.route(db, "bulk_extraction")
        if not ai.provider_available(provider):
            run.limitations.append("AI analysis unavailable (no API key); unstructured items kept with low confidence.")
            _event(db, run, "extract", "skipped", "AI enrichment skipped: provider not configured")
        else:
            for cand, _rec in candidates:
                try:
                    res = ai.complete_json(
                        db, agent="research_analyst", purpose=f"analyse feed item for {business.name}", role="bulk_extraction",
                        instructions=(f"Business context: {business.name} - {business.description[:400]}\n"
                                      "Assess the document's commercial relevance to this business and extract facts."),
                        documents=[{"source": cand.source_url or source.name, "text": f"{cand.title}\n{cand.summary}"}],
                        schema=ANALYSIS_SCHEMA, business_id=business.id, job_id=job_id, max_tokens=800,
                    )
                except BudgetExceeded as exc:
                    run.limitations.append(f"AI budget reached: {exc.reason}. Remaining items not analysed.")
                    _event(db, run, "extract", "warning", f"AI enrichment stopped: {exc.reason}")
                    break
                except ai.AIUnavailable as exc:
                    run.limitations.append(f"AI analysis failed: {exc}")
                    _event(db, run, "extract", "warning", f"AI enrichment failed: {exc}")
                    break
                cand.data["ai_analysis"] = {**res.data, "model": res.model, "cached": res.cached}
                cand.entity_name = cand.entity_name or res.data.get("entity_name")
                cand.extraction_confidence = 0.6
                cand.extracted_by = f"ai:{res.model}"
                stats["ai_enriched"] += 1
    check_cancel()

    # ---- Verify -------------------------------------------------------
    entity_checks: dict[str, dict] = {}
    if source.config.get("entity_verifier") == "texas_franchise_tax":
        names = sorted({c.entity_name for c, _ in candidates if c.entity_name})
        try:
            entity_checks = verifiers.texas_entity_lookup(http, names) if names else {}
            _event(db, run, "verify", "ok", f"Texas franchise-tax registry: {len(entity_checks)} of {len(names)} entities matched")
        except AdapterError as exc:
            run.limitations.append(f"Entity verification unavailable: {exc.limitation}")
            _event(db, run, "verify", "warning", f"Entity verification failed: {exc.limitation}")
            entity_checks = {}
            names = []
        checked = set(normalize_entity(n) for n in names)
    else:
        checked = set()
    _event(db, run, "verify", "ok", "Records retrieved directly from the official publisher" if source.official
           else "Source is not an official publisher; records marked unverified")

    # ---- Dedupe / Score / Qualify / Insert ---------------------------------
    now = datetime.now(timezone.utc)
    jur_cache: dict[str, Jurisdiction | None] = {}
    grouped: dict[str, list[tuple[Candidate, Any]]] = {}
    for cand, rec in candidates:
        grouped.setdefault(_dedupe_key(source, cand), []).append((cand, rec))
    _event(db, run, "dedupe", "ok", f"{len(candidates)} candidates collapsed to {len(grouped)} unique opportunities")

    touched: list[Opportunity] = []
    for fp, items in grouped.items():
        check_cancel()
        cand, rec = items[0]
        values = [c.reported_value for c, _ in items if c.reported_value is not None]
        reported = round(sum(values), 2) if values else None
        record_ids = sorted({r.external_id for _, r in items})
        opp = db.execute(select(Opportunity).where(Opportunity.business_id == source.business_id,
                                                   Opportunity.fingerprint == fp)).scalars().first()
        is_new = opp is None
        ent_norm = normalize_entity(cand.entity_name)
        ec = None
        if ent_norm in checked:
            row = entity_checks.get(ent_norm)
            ec = {"status": "match", "registry": "Texas Comptroller franchise tax", "record": row, "checked_at": now.isoformat()} if row \
                else {"status": "no_match", "registry": "Texas Comptroller franchise tax", "checked_at": now.isoformat()}
        data = {**cand.data, "records": record_ids, "record_count": len(items),
                "holder": source.config.get("holder"), "holder_type": source.config.get("holder_type"),
                "contacts": [c.__dict__ for c in cand.contacts], "extracted_by": cand.extracted_by,
                "assumed_service_rate": source.config.get("assumed_service_rate", 0.005)}
        if ec:
            data["entity_check"] = ec
        if is_new:
            opp = Opportunity(
                business_id=source.business_id, source_id=source.id, external_key=cand.external_key, fingerprint=fp,
                title=cand.title[:500], summary=cand.summary, category=cand.category, entity_name=cand.entity_name,
                entity_normalized=ent_norm or None, jurisdiction_code=cand.jurisdiction_code, location=cand.location,
                reported_value=reported, original_source=source.name, source_url=cand.source_url, retrieved_at=now,
                last_seen_at=now, deadline=cand.deadline, data=data, stage="discovered",
                verification_status="source_record_official" if source.official else "unverified",
                last_verified_at=now if source.official else None,
            )
            db.add(opp)
            db.flush()
            record_history(db, opp, "stage_change", AGENT, f"Discovered by research run #{run.id} from {source.name}",
                           to_stage="discovered")
            stats["new"] += 1
        else:
            changes = {}
            new_vals = {"reported_value": reported, "title": cand.title[:500], "location": cand.location,
                        "deadline": cand.deadline, "entity_name": cand.entity_name}
            for k in TRACKED_FIELDS:
                old = getattr(opp, k)
                if new_vals[k] is not None and old != new_vals[k]:
                    changes[k] = {"from": str(old) if old is not None else None, "to": str(new_vals[k])}
                    setattr(opp, k, new_vals[k])
            opp.data = {**(opp.data or {}), **data}
            opp.last_seen_at = now
            opp.retrieved_at = now
            if opp.is_stale:
                opp.is_stale = False
                changes["is_stale"] = {"from": "True", "to": "False"}
            if source.official:
                opp.last_verified_at = now
            if changes:
                record_history(db, opp, "updated", AGENT, f"Source data changed (run #{run.id})", changes=changes)
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1

        # Evidence (one source_record evidence per run per opportunity, hashed for change tracking)
        h = content_hash([r.data for _, r in items])
        if is_new or not any(e.content_hash == h for e in opp.evidence):
            db.add(Evidence(opportunity_id=opp.id, source_id=source.id, run_id=run.id, kind="source_record",
                            title=f"Record(s) from {source.name}", url=cand.source_url, content_hash=h,
                            excerpt=cand.excerpt[:1000], raw={"records": [r.data for _, r in items][:20]},
                            supports_verification=source.official))
        if ec and (is_new or "entity_check" not in (opp.data or {}) or ec["status"] == "match"):
            if ec["status"] == "match":
                db.add(Evidence(opportunity_id=opp.id, run_id=run.id, kind="entity_check",
                                title="Entity found in Texas Comptroller franchise-tax registry",
                                url=verifiers.TX_DATASET, excerpt=verifiers.texas_record_summary(ec["record"]),
                                raw=ec["record"], supports_verification=True))
        if cand.data.get("ai_analysis"):
            db.add(Evidence(opportunity_id=opp.id, run_id=run.id, kind="ai_analysis", is_ai_generated=True,
                            title=f"AI analysis ({cand.data['ai_analysis'].get('model')}) - not verified fact",
                            url=cand.source_url, excerpt=cand.data["ai_analysis"].get("summary", "")[:1000],
                            raw=cand.data["ai_analysis"]))
        if is_new:
            for c in cand.contacts[:5]:
                db.add(Contact(business_id=source.business_id, opportunity_id=opp.id, name=c.name[:255],
                               organization=c.organization, role=c.role, address=c.address, source="public_record",
                               source_url=cand.source_url, notes=f"From public record via {source.name}"))
        db.flush()
        touched.append(opp)

    # ---- Score / Qualify / Compliance --------------------------------------
    for opp in touched:
        if opp.stage not in ("discovered", "researching", "verified", "qualified"):
            continue
        jc = opp.jurisdiction_code
        if jc not in jur_cache:
            jur_cache[jc] = db.get(Jurisdiction, jc) if jc else None
        evaluate(db, opp, business, jur_cache[jc], settings, stats, actor="agent:opportunity_analyst")

    _event(db, run, "score", "ok", f"Scored {len(touched)} opportunities")
    _event(db, run, "qualify", "ok", f"{stats['qualified']} qualified, {stats['rejected']} rejected")
    _event(db, run, "insert", "ok", f"{stats['new']} new, {stats['updated']} updated, {stats['unchanged']} unchanged")

    source.cursor = fetched.new_cursor or source.cursor
    source.last_success_at = datetime.now(timezone.utc)
    source.last_error = None
    source.consecutive_failures = 0
    if source.status in ("failing",):
        source.status = "active"
    run.stats = stats
    run.status = "succeeded" if not run.limitations else "partial"
    run.finished_at = datetime.now(timezone.utc)
    _event(db, run, "complete", "ok", f"Run complete: {stats}")
    audit(db, AGENT, "research.run_completed", target_type="research_run", target_id=run.id,
          business_id=source.business_id, detail=stats)
    db.flush()
    return run


def evaluate(db: Session, opp: Opportunity, business: Business, jur: Jurisdiction | None, settings: dict,
             stats: dict | None = None, actor: str = "agent:opportunity_analyst") -> None:
    """Score an opportunity and move it through the internal research stages."""
    stats = stats if stats is not None else {}
    res = scoring.score(opp, business.slug, jur, settings)
    before = opp.score
    opp.score = res.score
    opp.score_breakdown = res.breakdown
    opp.confidence = res.confidence
    opp.estimated_value = res.estimated_value
    opp.estimated_value_basis = res.estimated_value_basis
    opp.estimated_cost = res.estimated_cost
    opp.expected_value = res.expected_value
    opp.recommended_action = res.recommended_action
    opp.risks = res.risks
    notes = compliance.review_opportunity(db, opp, business)
    opp.regulatory_notes = "\n".join(notes)
    if abs((before or 0) - res.score) >= 1 and opp.stage != "discovered":
        record_history(db, opp, "rescored", actor, f"Score {before:.1f} -> {res.score:.1f}")

    if opp.stage == "discovered":
        transition(db, opp, "researching", actor, "Automated research started")
    if res.reject_reason or res.score < business.reject_threshold:
        reason = res.reject_reason or f"Score {res.score:.1f} below rejection threshold {business.reject_threshold:.0f}"
        if opp.stage != "lost":
            transition(db, opp, "lost", actor, f"Auto-rejected: {reason}")
            stats["rejected"] = stats.get("rejected", 0) + 1
        return
    verified = opp.verification_status.startswith("source_record_official") or \
        (opp.data or {}).get("entity_check", {}).get("status") == "match"
    if verified and opp.stage == "researching":
        transition(db, opp, "verified", actor, "Record confirmed at official source")
        stats["verified"] = stats.get("verified", 0) + 1
    if opp.stage == "verified" and res.score >= business.qualify_threshold:
        transition(db, opp, "qualified", actor, f"Score {res.score:.1f} >= qualification threshold {business.qualify_threshold:.0f}")
        stats["qualified"] = stats.get("qualified", 0) + 1
    elif opp.stage == "qualified" and res.score < business.qualify_threshold:
        transition(db, opp, "verified", actor, f"Requalification: score fell to {res.score:.1f}")


def recommend_actions(db: Session, business: Business, *, limit: int, actor: str = "agent:pipeline_manager") -> dict[str, int]:
    """For top qualified opportunities: file approval requests when compliant; otherwise create owner tasks."""
    from ..pipeline import ApprovalError, request_approval

    out = {"approvals": 0, "tasks": 0}
    opps = db.execute(select(Opportunity).where(Opportunity.business_id == business.id, Opportunity.stage == "qualified",
                                                Opportunity.is_stale.is_(False))
                      .order_by(Opportunity.score.desc()).limit(limit * 3)).scalars().all()
    for opp in opps:
        if out["approvals"] >= limit:
            break
        if opp.category in MONITOR_ONLY_CATEGORIES:
            exists = db.execute(select(Task.id).where(Task.opportunity_id == opp.id)).first()
            if not exists:
                db.add(Task(business_id=business.id, opportunity_id=opp.id, title=f"Monitor: {opp.title[:150]}",
                            detail=opp.recommended_action, created_by=actor, due_on=opp.deadline.date() if opp.deadline else None))
                out["tasks"] += 1
            continue
        blockers = compliance.blockers_for(db, opp)
        if blockers:
            title = f"Resolve before outreach: {opp.title[:120]}"
            exists = db.execute(select(Task.id).where(Task.opportunity_id == opp.id, Task.status == "open")).first()
            if not exists:
                db.add(Task(business_id=business.id, opportunity_id=opp.id, title=title,
                            detail="Compliance blockers:\n- " + "\n- ".join(blockers), created_by="agent:compliance_analyst",
                            priority="high" if opp.score >= 75 else "normal"))
                out["tasks"] += 1
            continue
        evidence = "; ".join(f"{e.title} ({e.url})" for e in opp.evidence if not e.is_ai_generated)[:1500]
        try:
            request_approval(
                db, business_id=business.id, opportunity=opp, action_type="contact_prospect",
                proposed_action=(f"Send one introductory letter/email to {opp.entity_name or 'the identified party'} regarding: "
                                 f"{opp.title}. No agreement, fee or filing is authorized by this approval."),
                justification=f"Score {opp.score:.0f}/100, confidence {opp.confidence:.0%}. {opp.recommended_action}",
                evidence_summary=evidence or "See opportunity evidence.",
                expected_benefit=opp.estimated_value_basis or "Opportunity to qualify a commercial lead.",
                risks="; ".join(opp.risks) or "Standard outreach risks.",
                estimated_cost_usd=float(opp.estimated_cost or 0),
                requested_by=actor, payload={"opportunity_id": opp.id, "channel": "letter_or_email"},
            )
            out["approvals"] += 1
        except ApprovalError:
            continue
    return out
