"""Job handlers (Research Director orchestration and worker tasks)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from ..agents import compliance, executive, monitor
from ..app_settings import all_settings
from ..models import Business, Source
from ..research.base import AdapterError
from ..research.engine import recommend_actions, run_source
from ..research.http import ResearchHttp
from ..models import Job
from .scheduler import Deferred, JobContext, NonRetryable, enqueue, handler

# Allows tests to inject a mocked transport.
HTTP_FACTORY = ResearchHttp


@handler("research_source")
def research_source(ctx: JobContext) -> dict:
    db, job = ctx.db, ctx.job
    source = db.get(Source, job.source_id) if job.source_id else None
    if source is None:
        raise NonRetryable("Source not found")
    if not source.enabled:
        return {"skipped": "source disabled"}
    business = db.get(Business, source.business_id)
    if not business.automation_enabled:
        return {"skipped": "automation disabled for business"}
    http = HTTP_FACTORY()
    try:
        run = run_source(db, source, http, job_id=job.id, check_cancel=ctx.check_cancel,
                         max_records=job.payload.get("max_records"))
    except AdapterError as exc:
        db.commit()  # persist the failed run record + source status before the job is retried/failed
        if not exc.retryable:
            raise NonRetryable(exc.limitation) from exc
        raise
    finally:
        http.close()
    return {"run_id": run.id, "status": run.status, "stats": run.stats, "limitations": run.limitations}


@handler("source_discovery")
def source_discovery(ctx: JobContext) -> dict:
    db = ctx.db
    src = db.get(Source, ctx.job.source_id)
    http = HTTP_FACTORY()
    try:
        n = monitor.discover_sources(db, src, http)
    finally:
        http.close()
    return {"proposed_sources": n}


@handler("jurisdiction_portal_check")
def jurisdiction_portal_check(ctx: JobContext) -> dict:
    db = ctx.db
    http = HTTP_FACTORY()
    try:
        res = monitor.check_jurisdiction_portals(db, http, limit=ctx.job.payload.get("limit"))
    finally:
        http.close()
    b07 = db.execute(select(Business).where(Business.code == "B07")).scalars().first()
    if b07:
        res["alerts"] = compliance.jurisdiction_alerts(db, b07.id)
    return res


def _wait_for_research(ctx: JobContext, max_deferrals: int = 60) -> None:
    pending = ctx.db.execute(select(Job.id).where(Job.job_type == "research_source",
                                                  Job.status.in_(["queued", "running"]))).first()
    if pending and int(ctx.job.payload.get("deferrals", 0)) < max_deferrals:
        raise Deferred(60, "waiting for research jobs to finish")


@handler("pipeline_maintenance")
def pipeline_maintenance(ctx: JobContext) -> dict:
    """Pipeline Manager: stale detection, requalification, re-verification, next-action recommendations."""
    db = ctx.db
    _wait_for_research(ctx)
    settings = all_settings(db)
    out = {}
    q = select(Business).where(Business.status == "active", Business.automation_enabled.is_(True))
    if ctx.job.business_id:
        q = q.where(Business.id == ctx.job.business_id)
    http = HTTP_FACTORY()
    try:
        for b in db.execute(q).scalars():
            ctx.check_cancel()
            r = {"stale": monitor.detect_stale(db, b), "requalified": monitor.requalify(db, b),
                 "reverified": monitor.reverify(db, b, http, limit=ctx.job.payload.get("reverify_limit", 25))}
            if settings["auto_request_approvals"]:
                r["recommendations"] = recommend_actions(db, b, limit=int(settings["max_auto_approvals_per_cycle"]))
            out[b.code] = r
            ctx.heartbeat()
    finally:
        http.close()
    return out


@handler("research_cycle")
def research_cycle(ctx: JobContext) -> dict:
    """Research Director: enqueue all due research, ordered by business priority."""
    db = ctx.db
    rows = db.execute(select(Source, Business).join(Business, Source.business_id == Business.id)
                      .where(Source.enabled.is_(True), Source.status.in_(["active", "failing"]),
                             Source.adapter != "socrata_catalog", Business.automation_enabled.is_(True))
                      .order_by(Business.priority.asc())).all()
    queued = []
    for src, biz in rows:
        j = enqueue(db, "research_source", business_id=biz.id, source_id=src.id, priority=biz.priority,
                    triggered_by=f"job:{ctx.job.id}")
        queued.append(j.id)
    enqueue(db, "pipeline_maintenance", priority=8, triggered_by=f"job:{ctx.job.id}")
    enqueue(db, "executive_briefing", priority=9, triggered_by=f"job:{ctx.job.id}")
    return {"queued_research_jobs": len(queued)}


@handler("executive_briefing")
def executive_briefing(ctx: JobContext) -> dict:
    _wait_for_research(ctx)
    pm = ctx.db.execute(select(Job.id).where(Job.job_type == "pipeline_maintenance", Job.status.in_(["queued", "running"]))).first()
    if pm and int(ctx.job.payload.get("deferrals", 0)) < 60:
        raise Deferred(60, "waiting for pipeline maintenance")
    briefs = executive.generate(ctx.db, job_id=ctx.job.id)
    return {"briefings": [b.id for b in briefs], "generated_at": datetime.now(timezone.utc).isoformat()}


@handler("backup")
def backup_job(ctx: JobContext) -> dict:
    from ..backup import create_backup

    path = create_backup(label="scheduled")
    return {"backup": str(path.name)}
