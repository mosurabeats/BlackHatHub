"""Research sources, runs, jobs, schedules, jurisdictions and compliance alerts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select

from ..audit import audit
from ..deps import Ctx, get_ctx, get_scoped
from ..jobs.scheduler import cancel, enqueue
from ..models import ComplianceAlert, Job, Jurisdiction, ResearchEvent, ResearchRun, Schedule, Source
from . import serializers as S

router = APIRouter(prefix="/api", tags=["research"])


def _visible_job(ctx: Ctx, j: Job) -> bool:
    return ctx.scope.allows(j.business_id)


# ----------------------------------------------------------------------------- sources


@router.get("/sources")
def list_sources(ctx: Ctx = Depends(get_ctx), business_id: int | None = None):
    stmt = select(Source).where(Source.business_id.in_(ctx.scope.ids))
    if business_id:
        stmt = stmt.where(Source.business_id == business_id)
    return [S.source(s) for s in ctx.db.execute(stmt.order_by(Source.business_id, Source.id)).scalars()]


class SourcePatch(BaseModel):
    enabled: bool | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=120)
    fields: dict | None = None  # field mapping for proposed sources
    jurisdiction: str | None = Field(default=None, max_length=4)


@router.patch("/sources/{sid}")
def patch_source(sid: int, body: SourcePatch, ctx: Ctx = Depends(get_ctx)):
    s = get_scoped(ctx, Source, sid)
    if body.fields is not None:
        if not all(isinstance(k, str) and isinstance(v, (str, list)) for k, v in body.fields.items()):
            raise HTTPException(status_code=422, detail="Field mapping must map names to column names")
        s.config = {**s.config, "fields": body.fields}
    if body.jurisdiction is not None:
        s.config = {**s.config, "jurisdiction": body.jurisdiction.upper()}
        s.jurisdiction_code = body.jurisdiction.upper()
    if body.rate_limit_per_minute is not None:
        s.rate_limit_per_minute = body.rate_limit_per_minute
    if body.enabled is not None:
        if body.enabled and s.adapter == "socrata_dataset" and not (s.config.get("fields") or {}):
            raise HTTPException(status_code=422, detail="Configure the field mapping before enabling this source")
        s.enabled = body.enabled
        if body.enabled and s.status in ("proposed", "disabled", "failing"):
            s.status = "active"
        if not body.enabled:
            s.status = "disabled"
    audit(ctx.db, ctx.actor, "source.updated", target_type="source", target_id=s.id, business_id=s.business_id,
          detail=body.model_dump(exclude_none=True))
    ctx.db.commit()
    return S.source(s)


class RssSourceIn(BaseModel):
    business_id: int
    name: str = Field(min_length=3, max_length=200)
    url: HttpUrl
    keywords: list[str] = Field(default_factory=list, max_length=20)


@router.post("/sources/rss")
def add_rss_source(body: RssSourceIn, ctx: Ctx = Depends(get_ctx)):
    if not ctx.scope.allows(body.business_id):
        raise HTTPException(status_code=404, detail="Not found")
    key = f"rss:{body.business_id}:{abs(hash(str(body.url))) % 10**10}"
    if ctx.db.execute(select(Source.id).where(Source.key == key)).first():
        raise HTTPException(status_code=409, detail="Feed already added")
    s = Source(key=key, business_id=body.business_id, name=body.name, adapter="rss_feed", url=str(body.url),
               config={"url": str(body.url), "keywords": body.keywords, "category": "market_signal"}, official=False,
               discovered_by=ctx.actor)
    ctx.db.add(s)
    ctx.db.commit()
    return S.source(s)


@router.post("/sources/{sid}/run")
def run_source_now(sid: int, ctx: Ctx = Depends(get_ctx)):
    s = get_scoped(ctx, Source, sid)
    job_type = "source_discovery" if s.adapter == "socrata_catalog" else "research_source"
    j = enqueue(ctx.db, job_type, business_id=s.business_id, source_id=s.id, priority=2, triggered_by=ctx.actor)
    ctx.db.commit()
    return S.job(j)


@router.get("/runs")
def list_runs(ctx: Ctx = Depends(get_ctx), business_id: int | None = None, source_id: int | None = None, limit: int = 50):
    stmt = select(ResearchRun).where(ResearchRun.business_id.in_(ctx.scope.ids))
    if business_id:
        stmt = stmt.where(ResearchRun.business_id == business_id)
    if source_id:
        stmt = stmt.where(ResearchRun.source_id == source_id)
    return [S.run(r) for r in ctx.db.execute(stmt.order_by(ResearchRun.id.desc()).limit(min(limit, 200))).scalars()]


@router.get("/runs/{rid}")
def get_run(rid: int, ctx: Ctx = Depends(get_ctx)):
    r = get_scoped(ctx, ResearchRun, rid)
    events = ctx.db.execute(select(ResearchEvent).where(ResearchEvent.run_id == r.id).order_by(ResearchEvent.id)).scalars().all()
    return S.run(r, events)


# ----------------------------------------------------------------------------- jobs & schedules


@router.get("/jobs")
def list_jobs(ctx: Ctx = Depends(get_ctx), status: str | None = None, limit: int = 100):
    stmt = select(Job).where((Job.business_id.is_(None)) | (Job.business_id.in_(ctx.scope.ids)))
    if status:
        stmt = stmt.where(Job.status == status)
    return [S.job(j) for j in ctx.db.execute(stmt.order_by(Job.id.desc()).limit(min(limit, 300))).scalars()]


@router.post("/jobs/{jid}/cancel")
def cancel_job(jid: int, ctx: Ctx = Depends(get_ctx)):
    j = get_scoped(ctx, Job, jid)
    cancel(ctx.db, j)
    audit(ctx.db, ctx.actor, "job.cancel", target_type="job", target_id=j.id)
    ctx.db.commit()
    return S.job(j)


@router.post("/jobs/{jid}/retry")
def retry_job(jid: int, ctx: Ctx = Depends(get_ctx)):
    j = get_scoped(ctx, Job, jid)
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(status_code=409, detail="Only failed or cancelled jobs can be retried")
    nj = enqueue(ctx.db, j.job_type, business_id=j.business_id, source_id=j.source_id, payload=j.payload, priority=2,
                 triggered_by=ctx.actor)
    ctx.db.commit()
    return S.job(nj)


@router.post("/jobs/research-cycle")
def run_cycle_now(ctx: Ctx = Depends(get_ctx)):
    j = enqueue(ctx.db, "research_cycle", priority=1, triggered_by=ctx.actor)
    ctx.db.commit()
    return S.job(j)


@router.get("/schedules")
def list_schedules(ctx: Ctx = Depends(get_ctx)):
    stmt = select(Schedule).where((Schedule.business_id.is_(None)) | (Schedule.business_id.in_(ctx.scope.ids)))
    return [S.schedule(s) for s in ctx.db.execute(stmt.order_by(Schedule.next_run_at)).scalars()]


class SchedulePatch(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=15, le=60 * 24 * 31)


@router.patch("/schedules/{sid}")
def patch_schedule(sid: int, body: SchedulePatch, ctx: Ctx = Depends(get_ctx)):
    s = get_scoped(ctx, Schedule, sid)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    ctx.db.commit()
    return S.schedule(s)


@router.post("/schedules/{sid}/run-now")
def schedule_run_now(sid: int, ctx: Ctx = Depends(get_ctx)):
    s = get_scoped(ctx, Schedule, sid)
    s.next_run_at = datetime.now(timezone.utc)
    ctx.db.commit()
    return S.schedule(s)


# ----------------------------------------------------------------------------- jurisdictions


@router.get("/jurisdictions")
def list_jurisdictions(ctx: Ctx = Depends(get_ctx)):
    return [S.jurisdiction(j) for j in ctx.db.execute(select(Jurisdiction).order_by(Jurisdiction.name)).scalars()]


@router.get("/jurisdictions/{code}")
def get_jurisdiction(code: str, ctx: Ctx = Depends(get_ctx)):
    j = ctx.db.get(Jurisdiction, code.upper())
    if j is None:
        raise HTTPException(status_code=404, detail="Not found")
    return S.jurisdiction(j)


class Citation(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    url: HttpUrl


class JurisdictionPatch(BaseModel):
    agency_name: str | None = Field(default=None, max_length=255)
    agency_url: HttpUrl | None = None
    search_portal_url: HttpUrl | None = None
    data_availability: str | None = Field(default=None, max_length=4000)
    bulk_data_available: Literal["yes", "no", "unknown", "restricted"] | None = None
    finder_license_required: Literal["yes", "no", "unknown"] | None = None
    finder_registration: str | None = Field(default=None, max_length=4000)
    fee_restrictions: str | None = Field(default=None, max_length=4000)
    max_fee_percent: float | None = Field(default=None, ge=0, le=100)
    waiting_period: str | None = Field(default=None, max_length=4000)
    claimant_authorization_rules: str | None = Field(default=None, max_length=4000)
    contract_requirements: str | None = Field(default=None, max_length=4000)
    documentation_requirements: str | None = Field(default=None, max_length=4000)
    statutory_references: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=8000)
    add_citations: list[Citation] = Field(default_factory=list)
    compliance_review_status: Literal["unverified_seed", "in_review", "verified", "needs_update"] | None = None
    operating_status: Literal["not_cleared", "cleared", "prohibited"] | None = None


@router.patch("/jurisdictions/{code}")
def patch_jurisdiction(code: str, body: JurisdictionPatch, ctx: Ctx = Depends(get_ctx)):
    j = ctx.db.get(Jurisdiction, code.upper())
    if j is None:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_none=True, exclude={"add_citations"})
    for k, v in data.items():
        setattr(j, k, str(v) if k.endswith("_url") else v)
    if body.add_citations:
        j.source_citations = list(j.source_citations or []) + [{"title": c.title, "url": str(c.url), "added_by": ctx.actor,
                                                                 "added_at": datetime.now(timezone.utc).isoformat()} for c in body.add_citations]
    if body.compliance_review_status == "verified":
        official = [c for c in (j.source_citations or []) if c.get("added_by")]
        if not official:
            raise HTTPException(status_code=422, detail="Add at least one official citation (statute or agency guidance) before marking verified")
        j.last_verified_at = datetime.now(timezone.utc)
        j.verified_by = ctx.actor
    if body.operating_status == "cleared" and j.compliance_review_status != "verified":
        raise HTTPException(status_code=422, detail="A jurisdiction must be verified before it can be cleared for operation")
    audit(ctx.db, ctx.actor, "jurisdiction.updated", target_type="jurisdiction", target_id=j.code, detail=data)
    ctx.db.commit()
    return S.jurisdiction(j)


@router.post("/jurisdictions/check-portals")
def check_portals(ctx: Ctx = Depends(get_ctx)):
    j = enqueue(ctx.db, "jurisdiction_portal_check", priority=3, triggered_by=ctx.actor)
    ctx.db.commit()
    return S.job(j)


# ----------------------------------------------------------------------------- compliance


@router.get("/compliance/alerts")
def list_alerts(ctx: Ctx = Depends(get_ctx), status: str | None = "open"):
    stmt = select(ComplianceAlert).where(ComplianceAlert.business_id.in_(ctx.scope.ids))
    if status:
        stmt = stmt.where(ComplianceAlert.status == status)
    return [S.alert(a) for a in ctx.db.execute(stmt.order_by(ComplianceAlert.id.desc()).limit(300)).scalars()]


class AlertPatch(BaseModel):
    status: Literal["open", "acknowledged", "resolved"]


@router.patch("/compliance/alerts/{aid}")
def patch_alert(aid: int, body: AlertPatch, ctx: Ctx = Depends(get_ctx)):
    a = get_scoped(ctx, ComplianceAlert, aid)
    a.status = body.status
    ctx.db.commit()
    return S.alert(a)
