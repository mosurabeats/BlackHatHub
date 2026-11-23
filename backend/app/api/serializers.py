"""Explicit serializers (never dump ORM objects wholesale)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..models import STAGE_LABELS


def _iso(v: datetime | date | None) -> str | None:
    return v.isoformat() if v else None


def business(b, stats: dict | None = None) -> dict[str, Any]:
    return {"id": b.id, "code": b.code, "slug": b.slug, "name": b.name, "description": b.description,
            "is_private": b.is_private, "status": b.status, "priority": b.priority,
            "qualify_threshold": b.qualify_threshold, "reject_threshold": b.reject_threshold,
            "automation_enabled": b.automation_enabled, **({"stats": stats} if stats is not None else {})}


def opportunity(o, full: bool = False) -> dict[str, Any]:
    d = {
        "id": o.id, "business_id": o.business_id, "title": o.title, "summary": o.summary, "category": o.category,
        "entity_name": o.entity_name, "jurisdiction_code": o.jurisdiction_code, "location": o.location,
        "stage": o.stage, "stage_label": STAGE_LABELS.get(o.stage, o.stage), "score": o.score, "confidence": o.confidence,
        "reported_value": o.reported_value, "estimated_value": o.estimated_value, "estimated_value_basis": o.estimated_value_basis,
        "estimated_cost": o.estimated_cost, "expected_value": o.expected_value, "recommended_action": o.recommended_action,
        "original_source": o.original_source, "source_url": o.source_url, "retrieved_at": _iso(o.retrieved_at),
        "last_verified_at": _iso(o.last_verified_at), "verification_status": o.verification_status,
        "deadline": _iso(o.deadline), "is_stale": o.is_stale, "created_at": _iso(o.created_at), "updated_at": _iso(o.updated_at),
        "is_sample": o.is_sample,
    }
    if full:
        d.update({
            "score_breakdown": o.score_breakdown, "regulatory_notes": o.regulatory_notes, "risks": o.risks,
            "rejected_reason": o.rejected_reason, "first_seen_at": _iso(o.created_at), "last_seen_at": _iso(o.last_seen_at),
            "data": {k: v for k, v in (o.data or {}).items() if k not in ("contacts",)},
            "evidence": [evidence(e) for e in sorted(o.evidence, key=lambda e: e.retrieved_at, reverse=True)],
            "history": [history(h) for h in o.history],
        })
    return d


def evidence(e) -> dict[str, Any]:
    return {"id": e.id, "kind": e.kind, "title": e.title, "url": e.url, "retrieved_at": _iso(e.retrieved_at),
            "excerpt": e.excerpt, "is_ai_generated": e.is_ai_generated, "supports_verification": e.supports_verification,
            "content_hash": e.content_hash, "raw": e.raw}


def history(h) -> dict[str, Any]:
    return {"id": h.id, "at": _iso(h.at), "event": h.event, "from_stage": h.from_stage, "to_stage": h.to_stage,
            "actor": h.actor, "reason": h.reason, "changes": h.changes}


def approval(a) -> dict[str, Any]:
    return {"id": a.id, "business_id": a.business_id, "opportunity_id": a.opportunity_id, "action_type": a.action_type,
            "proposed_action": a.proposed_action, "payload": a.payload, "action_hash": a.action_hash,
            "justification": a.justification, "evidence_summary": a.evidence_summary, "expected_benefit": a.expected_benefit,
            "risks": a.risks, "estimated_cost_usd": a.estimated_cost_usd, "compliance_blockers": a.compliance_blockers,
            "requested_by": a.requested_by, "status": a.status, "decided_by": a.decided_by, "decided_at": _iso(a.decided_at),
            "decision_note": a.decision_note, "expires_at": _iso(a.expires_at), "executed_at": _iso(a.executed_at),
            "execution_result": a.execution_result, "created_at": _iso(a.created_at)}


def contact(c) -> dict[str, Any]:
    return {"id": c.id, "business_id": c.business_id, "opportunity_id": c.opportunity_id, "name": c.name,
            "organization": c.organization, "role": c.role, "email": c.email, "phone": c.phone, "address": c.address,
            "source": c.source, "source_url": c.source_url, "notes": c.notes, "created_at": _iso(c.created_at)}


def task(t) -> dict[str, Any]:
    return {"id": t.id, "business_id": t.business_id, "opportunity_id": t.opportunity_id, "title": t.title, "detail": t.detail,
            "status": t.status, "priority": t.priority, "due_on": _iso(t.due_on), "created_by": t.created_by,
            "created_at": _iso(t.created_at)}


def source(s) -> dict[str, Any]:
    return {"id": s.id, "key": s.key, "business_id": s.business_id, "name": s.name, "adapter": s.adapter, "url": s.url,
            "jurisdiction_code": s.jurisdiction_code, "official": s.official, "enabled": s.enabled, "status": s.status,
            "discovered_by": s.discovered_by, "access_notes": s.access_notes, "config": s.config,
            "last_run_at": _iso(s.last_run_at), "last_success_at": _iso(s.last_success_at), "last_error": s.last_error,
            "consecutive_failures": s.consecutive_failures, "rate_limit_per_minute": s.rate_limit_per_minute}


def run(r, events: list | None = None) -> dict[str, Any]:
    d = {"id": r.id, "job_id": r.job_id, "business_id": r.business_id, "source_id": r.source_id, "started_at": _iso(r.started_at),
         "finished_at": _iso(r.finished_at), "status": r.status, "current_stage": r.current_stage, "stats": r.stats,
         "error": r.error, "limitations": r.limitations}
    if events is not None:
        d["events"] = [{"at": _iso(e.at), "stage": e.stage, "status": e.status, "message": e.message, "data": e.data} for e in events]
    return d


def job(j) -> dict[str, Any]:
    return {"id": j.id, "job_type": j.job_type, "business_id": j.business_id, "source_id": j.source_id, "status": j.status,
            "priority": j.priority, "attempts": j.attempts, "max_attempts": j.max_attempts, "next_attempt_at": _iso(j.next_attempt_at),
            "created_at": _iso(j.created_at), "started_at": _iso(j.started_at), "finished_at": _iso(j.finished_at),
            "error": j.error, "result": {k: v for k, v in (j.result or {}).items() if k != "traceback"},
            "triggered_by": j.triggered_by, "recovered": j.recovered, "cancel_requested": j.cancel_requested}


def schedule(s) -> dict[str, Any]:
    return {"id": s.id, "key": s.key, "name": s.name, "job_type": s.job_type, "business_id": s.business_id,
            "interval_minutes": s.interval_minutes, "enabled": s.enabled, "next_run_at": _iso(s.next_run_at),
            "last_run_at": _iso(s.last_run_at), "missed_runs": s.missed_runs, "last_job_id": s.last_job_id}


def jurisdiction(j) -> dict[str, Any]:
    cols = ["code", "name", "agency_name", "agency_url", "search_portal_url", "data_availability", "bulk_data_available",
            "finder_license_required", "finder_registration", "fee_restrictions", "max_fee_percent", "waiting_period",
            "claimant_authorization_rules", "contract_requirements", "documentation_requirements", "statutory_references",
            "source_citations", "compliance_review_status", "verified_by", "portal_status", "portal_http_status",
            "operating_status", "notes"]
    d = {c: getattr(j, c) for c in cols}
    for c in ("last_verified_at", "portal_last_checked_at", "portal_changed_at", "updated_at"):
        d[c] = _iso(getattr(j, c))
    return d


def alert(a) -> dict[str, Any]:
    return {"id": a.id, "created_at": _iso(a.created_at), "business_id": a.business_id, "opportunity_id": a.opportunity_id,
            "jurisdiction_code": a.jurisdiction_code, "severity": a.severity, "code": a.code, "title": a.title,
            "detail": a.detail, "status": a.status}


def finance_entry(f) -> dict[str, Any]:
    return {"id": f.id, "business_id": f.business_id, "kind": f.kind, "category": f.category, "amount": f.amount,
            "occurred_on": _iso(f.occurred_on), "description": f.description, "opportunity_id": f.opportunity_id,
            "entered_by": f.entered_by}


def briefing(b, full: bool = True) -> dict[str, Any]:
    d = {"id": b.id, "created_at": _iso(b.created_at), "period_start": _iso(b.period_start), "period_end": _iso(b.period_end),
         "includes_private": b.includes_private, "generated_by": b.generated_by}
    if full:
        d.update({"content": b.content, "markdown": b.markdown, "ai_summary": b.ai_summary})
    else:
        c = b.content or {}
        d["headline"] = {"discovered": c.get("discovered", {}).get("total", 0),
                         "approvals": len(c.get("approvals_required", [])),
                         "rejected": c.get("rejected", {}).get("total", 0)}
    return d


def notification(n) -> dict[str, Any]:
    return {"id": n.id, "created_at": _iso(n.created_at), "business_id": n.business_id, "kind": n.kind, "severity": n.severity,
            "title": n.title, "body": n.body, "link": n.link, "read": n.read}
