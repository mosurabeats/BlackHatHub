"""Businesses, opportunities (pipeline), CRM contacts, tasks and approvals."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ..agents import compliance
from ..app_settings import all_settings
from ..audit import audit
from ..deps import Ctx, get_ctx, get_scoped, require_scope_business
from ..models import (
    APPROVAL_ACTION_TYPES,
    PIPELINE_STAGES,
    STAGE_LABELS,
    Approval,
    Business,
    ComplianceAlert,
    Contact,
    Evidence,
    Jurisdiction,
    Opportunity,
    ResearchRun,
    Source,
    Task,
)
from ..pipeline import ApprovalError, TransitionError, decide_approval, mark_executed, record_history, request_approval, transition
from ..research.engine import evaluate
from ..research.normalize import fingerprint, normalize_entity
from . import serializers as S

router = APIRouter(prefix="/api", tags=["core"])

OPEN_STAGES = [s for s in PIPELINE_STAGES if s not in ("won", "lost")]


def _business_by_slug(ctx: Ctx, slug: str) -> Business:
    b = ctx.db.execute(select(Business).where(Business.slug == slug)).scalars().first()
    if b is None or not ctx.scope.allows(b.id):
        raise HTTPException(status_code=404, detail="Not found")
    return b


def business_stats(ctx: Ctx, b: Business) -> dict:
    db = ctx.db
    counts = dict(db.execute(select(Opportunity.stage, func.count(Opportunity.id)).where(Opportunity.business_id == b.id)
                             .group_by(Opportunity.stage)).all())
    qualified_ev = db.execute(select(func.coalesce(func.sum(Opportunity.expected_value), 0.0)).where(
        Opportunity.business_id == b.id, Opportunity.stage.in_(["qualified", "awaiting_approval", "outreach_approved", "contacted", "negotiating", "active"]),
        Opportunity.expected_value > 0)).scalar_one()
    return {
        "stage_counts": {s: counts.get(s, 0) for s in PIPELINE_STAGES},
        "open_opportunities": sum(counts.get(s, 0) for s in OPEN_STAGES),
        "qualified_expected_value_estimate": round(float(qualified_ev), 2),
        "pending_approvals": db.execute(select(func.count(Approval.id)).where(Approval.business_id == b.id, Approval.status == "pending")).scalar_one(),
        "open_tasks": db.execute(select(func.count(Task.id)).where(Task.business_id == b.id, Task.status == "open")).scalar_one(),
        "open_alerts": db.execute(select(func.count(ComplianceAlert.id)).where(ComplianceAlert.business_id == b.id, ComplianceAlert.status == "open")).scalar_one(),
        "sources": db.execute(select(func.count(Source.id)).where(Source.business_id == b.id)).scalar_one(),
        "sources_enabled": db.execute(select(func.count(Source.id)).where(Source.business_id == b.id, Source.enabled.is_(True))).scalar_one(),
        "last_run": S.run(r) if (r := db.execute(select(ResearchRun).where(ResearchRun.business_id == b.id).order_by(ResearchRun.id.desc())).scalars().first()) else None,
    }


# ----------------------------------------------------------------------------- businesses


@router.get("/businesses")
def list_businesses(ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.execute(select(Business).where(Business.id.in_(ctx.scope.ids)).order_by(Business.sort_order)).scalars()
    return [S.business(b, business_stats(ctx, b)) for b in rows]


@router.get("/businesses/{slug}")
def get_business(slug: str, ctx: Ctx = Depends(get_ctx)):
    b = _business_by_slug(ctx, slug)
    return S.business(b, business_stats(ctx, b))


class BusinessPatch(BaseModel):
    automation_enabled: bool | None = None
    qualify_threshold: float | None = Field(default=None, ge=0, le=100)
    reject_threshold: float | None = Field(default=None, ge=0, le=100)
    status: Literal["active", "paused"] | None = None


@router.patch("/businesses/{slug}")
def patch_business(slug: str, body: BusinessPatch, ctx: Ctx = Depends(get_ctx)):
    b = _business_by_slug(ctx, slug)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(b, k, v)
    audit(ctx.db, ctx.actor, "business.updated", target_type="business", target_id=b.id, business_id=b.id, detail=body.model_dump(exclude_none=True))
    ctx.db.commit()
    return S.business(b)


# ----------------------------------------------------------------------------- opportunities


@router.get("/opportunities")
def list_opportunities(
    ctx: Ctx = Depends(get_ctx),
    business: str | None = None,
    stage: str | None = None,
    open_only: bool = False,
    q: str | None = Query(default=None, max_length=200),
    sort: Literal["score", "created", "value", "deadline"] = "score",
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    stmt = select(Opportunity).where(Opportunity.business_id.in_(ctx.scope.ids))
    if business:
        stmt = stmt.where(Opportunity.business_id == _business_by_slug(ctx, business).id)
    if stage:
        stmt = stmt.where(Opportunity.stage == stage)
    if open_only:
        stmt = stmt.where(Opportunity.stage.in_(OPEN_STAGES))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Opportunity.title.ilike(like), Opportunity.entity_name.ilike(like), Opportunity.summary.ilike(like)))
    order = {"score": Opportunity.score.desc(), "created": Opportunity.created_at.desc(),
             "value": Opportunity.reported_value.desc().nullslast(), "deadline": Opportunity.deadline.asc().nullslast()}[sort]
    total = ctx.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = ctx.db.execute(stmt.order_by(order, Opportunity.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"total": total, "items": [S.opportunity(o) for o in rows]}


@router.get("/opportunities/{opp_id}")
def get_opportunity(opp_id: int, ctx: Ctx = Depends(get_ctx)):
    o = get_scoped(ctx, Opportunity, opp_id)
    d = S.opportunity(o, full=True)
    d["approvals"] = [S.approval(a) for a in ctx.db.execute(select(Approval).where(Approval.opportunity_id == o.id).order_by(Approval.id.desc())).scalars()]
    d["contacts"] = [S.contact(c) for c in ctx.db.execute(select(Contact).where(Contact.opportunity_id == o.id)).scalars()]
    d["tasks"] = [S.task(t) for t in ctx.db.execute(select(Task).where(Task.opportunity_id == o.id)).scalars()]
    d["compliance_blockers"] = compliance.blockers_for(ctx.db, o)
    d["jurisdiction"] = S.jurisdiction(j) if o.jurisdiction_code and (j := ctx.db.get(Jurisdiction, o.jurisdiction_code)) else None
    d["business"] = S.business(ctx.db.get(Business, o.business_id))
    return d


class TransitionIn(BaseModel):
    stage: str
    reason: str = Field(default="", max_length=2000)


@router.post("/opportunities/{opp_id}/transition")
def transition_opportunity(opp_id: int, body: TransitionIn, ctx: Ctx = Depends(get_ctx)):
    o = get_scoped(ctx, Opportunity, opp_id)
    try:
        transition(ctx.db, o, body.stage, ctx.actor, body.reason)
    except TransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    audit(ctx.db, ctx.actor, "opportunity.transition", target_type="opportunity", target_id=o.id, business_id=o.business_id,
          detail={"to": body.stage})
    ctx.db.commit()
    return S.opportunity(o, full=True)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


@router.post("/opportunities/{opp_id}/notes")
def add_note(opp_id: int, body: NoteIn, ctx: Ctx = Depends(get_ctx)):
    o = get_scoped(ctx, Opportunity, opp_id)
    ctx.db.add(Evidence(opportunity_id=o.id, kind="owner_note", title="Owner note", excerpt=body.text))
    record_history(ctx.db, o, "note", ctx.actor, body.text[:500])
    ctx.db.commit()
    return {"ok": True}


@router.post("/opportunities/{opp_id}/rescore")
def rescore(opp_id: int, ctx: Ctx = Depends(get_ctx)):
    o = get_scoped(ctx, Opportunity, opp_id)
    if o.stage not in ("discovered", "researching", "verified", "qualified"):
        raise HTTPException(status_code=409, detail="Only opportunities in research stages can be rescored")
    b = ctx.db.get(Business, o.business_id)
    evaluate(ctx.db, o, b, ctx.db.get(Jurisdiction, o.jurisdiction_code) if o.jurisdiction_code else None, all_settings(ctx.db),
             actor=ctx.actor)
    ctx.db.commit()
    return S.opportunity(o, full=True)


class ManualOpportunityIn(BaseModel):
    business: str
    title: str = Field(min_length=3, max_length=500)
    summary: str = Field(default="", max_length=5000)
    entity_name: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    reported_value: float | None = None
    jurisdiction_code: str | None = Field(default=None, max_length=4)


@router.post("/opportunities")
def create_manual_opportunity(body: ManualOpportunityIn, ctx: Ctx = Depends(get_ctx)):
    """Owner-entered lead (optional; research normally creates these). Marked as owner-sourced and unverified."""
    b = _business_by_slug(ctx, body.business)
    fp = fingerprint("manual", body.title, body.entity_name or "")
    if ctx.db.execute(select(Opportunity.id).where(Opportunity.business_id == b.id, Opportunity.fingerprint == fp)).first():
        raise HTTPException(status_code=409, detail="Duplicate opportunity")
    o = Opportunity(business_id=b.id, external_key=f"manual:{fp[:12]}", fingerprint=fp, title=body.title, summary=body.summary,
                    entity_name=body.entity_name, entity_normalized=normalize_entity(body.entity_name) or None,
                    jurisdiction_code=body.jurisdiction_code, reported_value=body.reported_value, source_url=body.source_url,
                    original_source="Owner entry", category="manual", verification_status="unverified", data={})
    ctx.db.add(o)
    ctx.db.flush()
    record_history(ctx.db, o, "stage_change", ctx.actor, "Created manually by owner", to_stage="discovered")
    ctx.db.commit()
    return S.opportunity(o, full=True)


class ApprovalRequestIn(BaseModel):
    action_type: str
    proposed_action: str = Field(min_length=5, max_length=5000)
    justification: str = Field(min_length=3, max_length=5000)
    expected_benefit: str = Field(min_length=3, max_length=2000)
    risks: str = Field(min_length=3, max_length=2000)
    estimated_cost_usd: float = Field(default=0, ge=0)


@router.post("/opportunities/{opp_id}/request-approval")
def owner_request_approval(opp_id: int, body: ApprovalRequestIn, ctx: Ctx = Depends(get_ctx)):
    o = get_scoped(ctx, Opportunity, opp_id)
    if body.action_type not in APPROVAL_ACTION_TYPES:
        raise HTTPException(status_code=422, detail="Unknown action type")
    try:
        ap = request_approval(ctx.db, business_id=o.business_id, opportunity=o, action_type=body.action_type,
                              proposed_action=body.proposed_action, justification=body.justification,
                              evidence_summary="; ".join(f"{e.title} ({e.url})" for e in o.evidence if not e.is_ai_generated)[:1500],
                              expected_benefit=body.expected_benefit, risks=body.risks, estimated_cost_usd=body.estimated_cost_usd,
                              requested_by=ctx.actor, payload={"opportunity_id": o.id})
        ap.compliance_blockers = compliance.blockers_for(ctx.db, o)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    ctx.db.commit()
    return S.approval(ap)


@router.get("/pipeline/summary")
def pipeline_summary(ctx: Ctx = Depends(get_ctx), business: str | None = None):
    ids = [_business_by_slug(ctx, business).id] if business else ctx.scope.ids
    rows = ctx.db.execute(select(Opportunity.stage, func.count(Opportunity.id), func.coalesce(func.sum(Opportunity.reported_value), 0.0),
                                 func.coalesce(func.sum(Opportunity.expected_value), 0.0))
                          .where(Opportunity.business_id.in_(ids)).group_by(Opportunity.stage)).all()
    by = {r[0]: r for r in rows}
    return [{"stage": s, "label": STAGE_LABELS[s], "count": by[s][1] if s in by else 0,
             "reported_value_total": round(by[s][2], 2) if s in by else 0.0,
             "expected_value_estimate_total": round(by[s][3], 2) if s in by else 0.0} for s in PIPELINE_STAGES]


# ----------------------------------------------------------------------------- contacts & tasks


class ContactIn(BaseModel):
    business: str
    name: str = Field(min_length=1, max_length=255)
    organization: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    notes: str = Field(default="", max_length=5000)
    opportunity_id: int | None = None


@router.get("/contacts")
def list_contacts(ctx: Ctx = Depends(get_ctx), business: str | None = None, q: str | None = Query(default=None, max_length=200)):
    stmt = select(Contact).where(Contact.business_id.in_(ctx.scope.ids))
    if business:
        stmt = stmt.where(Contact.business_id == _business_by_slug(ctx, business).id)
    if q:
        stmt = stmt.where(or_(Contact.name.ilike(f"%{q}%"), Contact.organization.ilike(f"%{q}%")))
    return [S.contact(c) for c in ctx.db.execute(stmt.order_by(Contact.id.desc()).limit(500)).scalars()]


@router.post("/contacts")
def create_contact(body: ContactIn, ctx: Ctx = Depends(get_ctx)):
    b = _business_by_slug(ctx, body.business)
    if body.opportunity_id:
        o = get_scoped(ctx, Opportunity, body.opportunity_id)
        if o.business_id != b.id:
            raise HTTPException(status_code=422, detail="Opportunity belongs to another business")
    c = Contact(business_id=b.id, source="manual", **body.model_dump(exclude={"business"}))
    ctx.db.add(c)
    ctx.db.commit()
    return S.contact(c)


@router.delete("/contacts/{cid}")
def delete_contact(cid: int, ctx: Ctx = Depends(get_ctx)):
    c = get_scoped(ctx, Contact, cid)
    ctx.db.delete(c)
    ctx.db.commit()
    return {"ok": True}


class TaskIn(BaseModel):
    business: str
    title: str = Field(min_length=1, max_length=255)
    detail: str = Field(default="", max_length=5000)
    priority: Literal["low", "normal", "high"] = "normal"
    due_on: date | None = None
    opportunity_id: int | None = None


class TaskPatch(BaseModel):
    status: Literal["open", "done", "cancelled"] | None = None
    title: str | None = Field(default=None, max_length=255)
    priority: Literal["low", "normal", "high"] | None = None
    due_on: date | None = None


@router.get("/tasks")
def list_tasks(ctx: Ctx = Depends(get_ctx), business: str | None = None, status: str | None = "open"):
    stmt = select(Task).where(Task.business_id.in_(ctx.scope.ids))
    if business:
        stmt = stmt.where(Task.business_id == _business_by_slug(ctx, business).id)
    if status:
        stmt = stmt.where(Task.status == status)
    return [S.task(t) for t in ctx.db.execute(stmt.order_by(Task.due_on.asc().nullslast(), Task.id.desc()).limit(500)).scalars()]


@router.post("/tasks")
def create_task(body: TaskIn, ctx: Ctx = Depends(get_ctx)):
    b = _business_by_slug(ctx, body.business)
    if body.opportunity_id:
        get_scoped(ctx, Opportunity, body.opportunity_id)
    t = Task(business_id=b.id, created_by=ctx.actor, **body.model_dump(exclude={"business"}))
    ctx.db.add(t)
    ctx.db.commit()
    return S.task(t)


@router.patch("/tasks/{tid}")
def patch_task(tid: int, body: TaskPatch, ctx: Ctx = Depends(get_ctx)):
    t = get_scoped(ctx, Task, tid)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    ctx.db.commit()
    return S.task(t)


# ----------------------------------------------------------------------------- approvals


@router.get("/approvals")
def list_approvals(ctx: Ctx = Depends(get_ctx), status: str | None = "pending", business: str | None = None):
    stmt = select(Approval).where(Approval.business_id.in_(ctx.scope.ids))
    if status:
        stmt = stmt.where(Approval.status == status)
    if business:
        stmt = stmt.where(Approval.business_id == _business_by_slug(ctx, business).id)
    return [S.approval(a) for a in ctx.db.execute(stmt.order_by(Approval.id.desc()).limit(300)).scalars()]


@router.get("/approvals/{aid}")
def get_approval(aid: int, ctx: Ctx = Depends(get_ctx)):
    a = get_scoped(ctx, Approval, aid)
    d = S.approval(a)
    if a.opportunity_id:
        o = ctx.db.get(Opportunity, a.opportunity_id)
        d["opportunity"] = S.opportunity(o) if o else None
        d["current_compliance_blockers"] = compliance.blockers_for(ctx.db, o) if o else []
    return d


class DecisionIn(BaseModel):
    note: str = Field(default="", max_length=2000)
    confirm_hash: str | None = Field(default=None, max_length=64)


@router.post("/approvals/{aid}/approve")
def approve(aid: int, body: DecisionIn, ctx: Ctx = Depends(get_ctx)):
    a = get_scoped(ctx, Approval, aid)
    if a.opportunity_id:
        o = ctx.db.get(Opportunity, a.opportunity_id)
        if o is not None:
            a.compliance_blockers = compliance.blockers_for(ctx.db, o)  # re-evaluated at decision time
    try:
        decide_approval(ctx.db, a, approve=True, actor=ctx.actor, note=body.note, confirm_hash=body.confirm_hash)
    except ApprovalError as exc:
        ctx.db.commit()
        raise HTTPException(status_code=409, detail=str(exc))
    ctx.db.commit()
    return S.approval(a)


@router.post("/approvals/{aid}/reject")
def reject(aid: int, body: DecisionIn, ctx: Ctx = Depends(get_ctx)):
    a = get_scoped(ctx, Approval, aid)
    try:
        decide_approval(ctx.db, a, approve=False, actor=ctx.actor, note=body.note)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    ctx.db.commit()
    return S.approval(a)


class ExecutedIn(BaseModel):
    result: str = Field(min_length=3, max_length=5000)


@router.post("/approvals/{aid}/executed")
def executed(aid: int, body: ExecutedIn, ctx: Ctx = Depends(get_ctx)):
    a = get_scoped(ctx, Approval, aid)
    try:
        mark_executed(ctx.db, a, actor=ctx.actor, result=body.result)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    ctx.db.commit()
    return S.approval(a)


@router.post("/approvals/{aid}/cancel")
def cancel_approval(aid: int, ctx: Ctx = Depends(get_ctx)):
    a = get_scoped(ctx, Approval, aid)
    if a.status not in ("pending", "approved"):
        raise HTTPException(status_code=409, detail=f"Approval is {a.status}")
    a.status = "cancelled"
    if a.opportunity_id:
        o = ctx.db.get(Opportunity, a.opportunity_id)
        if o and o.stage == "awaiting_approval":
            o.stage = "qualified"
            record_history(ctx.db, o, "stage_change", ctx.actor, f"Approval #{a.id} cancelled", from_stage="awaiting_approval", to_stage="qualified")
    audit(ctx.db, ctx.actor, "approval.cancelled", target_type="approval", target_id=a.id, business_id=a.business_id)
    ctx.db.commit()
    return S.approval(a)
