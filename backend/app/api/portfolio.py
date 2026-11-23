"""Dashboard, finance, costs, settings, briefings, search, exports, notifications, system."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ..ai.budget import spend_summary
from ..ai.client import provider_available
from ..app_settings import DEFAULTS, all_settings, set_setting
from ..audit import audit
from ..backup import create_backup, list_backups, restore_backup
from ..config import get_settings
from ..deps import Ctx, get_ctx, get_scoped
from ..jobs.scheduler import enqueue, get_scheduler
from ..models import (
    AIUsage,
    Approval,
    AuditLog,
    Briefing,
    Business,
    ComplianceAlert,
    Contact,
    FinancialEntry,
    Forecast,
    Job,
    Notification,
    Opportunity,
    Schedule,
    Source,
    Task,
    WorkerHeartbeat,
)
from ..security import verify_secret
from . import serializers as S

router = APIRouter(prefix="/api", tags=["portfolio"])
ACTIVE_PIPE = ["qualified", "awaiting_approval", "outreach_approved", "contacted", "negotiating", "active"]


def _month_start(d: date | None = None) -> date:
    d = d or datetime.now(timezone.utc).date()
    return d.replace(day=1)


def _actuals(ctx: Ctx, ids: list[int], since: date | None = None) -> dict[str, float]:
    out = {"revenue": 0.0, "expense": 0.0}
    stmt = select(FinancialEntry.kind, func.coalesce(func.sum(FinancialEntry.amount), 0.0)).where(FinancialEntry.business_id.in_(ids))
    if since:
        stmt = stmt.where(FinancialEntry.occurred_on >= since)
    for kind, total in ctx.db.execute(stmt.group_by(FinancialEntry.kind)).all():
        out[kind] = round(float(total), 2)
    return out


def system_health(ctx: Ctx) -> dict[str, Any]:
    db = ctx.db
    s = get_settings()
    now = datetime.now(timezone.utc)
    hb = db.execute(select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_beat_at.desc())).scalars().first()
    alive = bool(hb and hb.status == "running" and now - hb.last_beat_at < timedelta(seconds=s.scheduler_poll_seconds * 3 + 60))
    day_ago = now - timedelta(days=1)
    job_filter = (Job.business_id.is_(None)) | (Job.business_id.in_(ctx.scope.ids))
    failing = db.execute(select(func.count(Source.id)).where(Source.business_id.in_(ctx.scope.ids), Source.enabled.is_(True),
                                                             Source.status.in_(["failing", "needs_credentials"]))).scalar_one()
    backups = list_backups() if s.resolved_database_url.startswith("sqlite") else []
    return {
        "scheduler": {"alive": alive, "worker_id": hb.worker_id if hb else None, "last_beat_at": hb.last_beat_at.isoformat() if hb else None,
                      "in_process": get_scheduler() is not None},
        "jobs": {
            "running": db.execute(select(func.count(Job.id)).where(job_filter, Job.status == "running")).scalar_one(),
            "queued": db.execute(select(func.count(Job.id)).where(job_filter, Job.status.in_(["queued", "retry_wait"]))).scalar_one(),
            "succeeded_24h": db.execute(select(func.count(Job.id)).where(job_filter, Job.status == "succeeded", Job.finished_at >= day_ago)).scalar_one(),
            "failed_24h": db.execute(select(func.count(Job.id)).where(job_filter, Job.status == "failed", Job.finished_at >= day_ago)).scalar_one(),
            "recovered_total": db.execute(select(func.count(Job.id)).where(job_filter, Job.recovered.is_(True))).scalar_one(),
        },
        "missed_schedule_runs": int(db.execute(select(func.coalesce(func.sum(Schedule.missed_runs), 0))).scalar_one()),
        "sources_needing_attention": failing,
        "ai": {"anthropic_configured": provider_available("anthropic"), "openai_configured": provider_available("openai")},
        "credentials": {"sam_gov": bool(s.sam_gov_api_key), "socrata_app_token": bool(s.socrata_app_token)},
        "database": {"engine": s.resolved_database_url.split(":", 1)[0]},
        "last_backup": backups[0] if backups else None,
    }


# ----------------------------------------------------------------------------- dashboard


@router.get("/dashboard")
def dashboard(ctx: Ctx = Depends(get_ctx)):
    db, ids = ctx.db, ctx.scope.ids
    now = datetime.now(timezone.utc)
    week = now - timedelta(days=7)
    in_scope = Opportunity.business_id.in_(ids)
    top = db.execute(select(Opportunity).where(in_scope, Opportunity.stage.in_(ACTIVE_PIPE)).order_by(Opportunity.score.desc()).limit(8)).scalars().all()
    bmap = {b.id: b for b in db.execute(select(Business).where(Business.id.in_(ids))).scalars()}
    month = _actuals(ctx, ids, _month_start())
    ytd = _actuals(ctx, ids, date(now.year, 1, 1))
    spend = spend_summary(db, business_ids=ids)
    latest = db.execute(select(Briefing).where(Briefing.includes_private.is_(ctx.scope.vault_unlocked)).order_by(Briefing.id.desc())).scalars().first()
    job_filter = (Job.business_id.is_(None)) | (Job.business_id.in_(ids))
    return {
        "vault_unlocked": ctx.scope.vault_unlocked,
        "active_businesses": sum(1 for b in bmap.values() if b.status == "active"),
        "new_opportunities_7d": db.execute(select(func.count(Opportunity.id)).where(in_scope, Opportunity.created_at >= week)).scalar_one(),
        "open_opportunities": db.execute(select(func.count(Opportunity.id)).where(in_scope, Opportunity.stage.notin_(["won", "lost"]))).scalar_one(),
        "qualified_pipeline": {
            "count": db.execute(select(func.count(Opportunity.id)).where(in_scope, Opportunity.stage.in_(ACTIVE_PIPE))).scalar_one(),
            "expected_value_estimate": round(float(db.execute(select(func.coalesce(func.sum(Opportunity.expected_value), 0.0))
                                                             .where(in_scope, Opportunity.stage.in_(ACTIVE_PIPE), Opportunity.expected_value > 0)).scalar_one()), 2),
            "reported_value_total": round(float(db.execute(select(func.coalesce(func.sum(Opportunity.reported_value), 0.0))
                                                          .where(in_scope, Opportunity.stage.in_(ACTIVE_PIPE))).scalar_one()), 2),
            "label": "ESTIMATE - speculative opportunity value, not revenue",
        },
        "top_opportunities": [{**S.opportunity(o), "business_name": bmap[o.business_id].name, "business_slug": bmap[o.business_id].slug} for o in top],
        "research_jobs": {
            "completed_24h": db.execute(select(func.count(Job.id)).where(job_filter, Job.status == "succeeded", Job.finished_at >= now - timedelta(days=1))).scalar_one(),
            "running": db.execute(select(func.count(Job.id)).where(job_filter, Job.status == "running")).scalar_one(),
            "queued": db.execute(select(func.count(Job.id)).where(job_filter, Job.status.in_(["queued", "retry_wait"]))).scalar_one(),
            "failed_24h": db.execute(select(func.count(Job.id)).where(job_filter, Job.status == "failed", Job.finished_at >= now - timedelta(days=1))).scalar_one(),
        },
        "pending_approvals": db.execute(select(func.count(Approval.id)).where(Approval.business_id.in_(ids), Approval.status == "pending")).scalar_one(),
        "open_tasks": db.execute(select(func.count(Task.id)).where(Task.business_id.in_(ids), Task.status == "open")).scalar_one(),
        "regulatory_alerts": db.execute(select(func.count(ComplianceAlert.id)).where(ComplianceAlert.business_id.in_(ids), ComplianceAlert.status == "open")).scalar_one(),
        "financials": {"month": {**month, "profit": round(month["revenue"] - month["expense"], 2)},
                       "ytd": {**ytd, "profit": round(ytd["revenue"] - ytd["expense"], 2)}, "label": "ACTUAL - owner-entered"},
        "ai_costs": spend,
        "system_health": system_health(ctx),
        "latest_briefing": S.briefing(latest, full=False) if latest else None,
        "businesses": [{"slug": b.slug, "name": b.name, "code": b.code, "is_private": b.is_private,
                        "open": db.execute(select(func.count(Opportunity.id)).where(Opportunity.business_id == b.id, Opportunity.stage.notin_(["won", "lost"]))).scalar_one(),
                        "qualified": db.execute(select(func.count(Opportunity.id)).where(Opportunity.business_id == b.id, Opportunity.stage.in_(ACTIVE_PIPE))).scalar_one()}
                       for b in sorted(bmap.values(), key=lambda b: b.sort_order)],
    }


# ----------------------------------------------------------------------------- finance


class FinanceIn(BaseModel):
    business_id: int
    kind: Literal["revenue", "expense"]
    category: str = Field(default="general", max_length=64)
    amount: float = Field(gt=0, le=1e10)
    occurred_on: date
    description: str = Field(default="", max_length=2000)
    opportunity_id: int | None = None


class ForecastIn(BaseModel):
    business_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    revenue: float = Field(default=0, ge=0)
    expenses: float = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=2000)


@router.get("/finance/summary")
def finance_summary(ctx: Ctx = Depends(get_ctx)):
    db, ids = ctx.db, ctx.scope.ids
    today = datetime.now(timezone.utc).date()
    start = (today.replace(day=1) - timedelta(days=330)).replace(day=1)
    per_business = []
    for b in db.execute(select(Business).where(Business.id.in_(ids)).order_by(Business.sort_order)).scalars():
        act = _actuals(ctx, [b.id])
        ai_cost = float(db.execute(select(func.coalesce(func.sum(AIUsage.cost_usd), 0.0)).where(AIUsage.business_id == b.id, AIUsage.status == "ok")).scalar_one())
        pipe = db.execute(select(func.coalesce(func.sum(Opportunity.expected_value), 0.0)).where(
            Opportunity.business_id == b.id, Opportunity.stage.in_(ACTIVE_PIPE), Opportunity.expected_value > 0)).scalar_one()
        fc = db.execute(select(func.coalesce(func.sum(Forecast.revenue), 0.0), func.coalesce(func.sum(Forecast.expenses), 0.0))
                        .where(Forecast.business_id == b.id, Forecast.period >= today.strftime("%Y-%m"))).one()
        per_business.append({
            "business_id": b.id, "name": b.name, "slug": b.slug, "is_private": b.is_private,
            "actual": {"revenue": act["revenue"], "expenses": act["expense"], "profit": round(act["revenue"] - act["expense"], 2)},
            "ai_cost_attributed": round(ai_cost, 4),
            "pipeline_expected_value_estimate": round(float(pipe), 2),
            "forecast_future": {"revenue": round(float(fc[0]), 2), "expenses": round(float(fc[1]), 2)},
        })
    series: dict[str, dict[str, float]] = {}
    for kind, d, amt in db.execute(select(FinancialEntry.kind, FinancialEntry.occurred_on, FinancialEntry.amount)
                                   .where(FinancialEntry.business_id.in_(ids), FinancialEntry.occurred_on >= start)).all():
        m = d.strftime("%Y-%m")
        series.setdefault(m, {"revenue": 0.0, "expense": 0.0})[kind] += amt
    months = []
    cur = start
    while cur <= today:
        m = cur.strftime("%Y-%m")
        months.append({"month": m, **{k: round(v, 2) for k, v in series.get(m, {"revenue": 0.0, "expense": 0.0}).items()}})
        cur = (cur + timedelta(days=32)).replace(day=1)
    tot = _actuals(ctx, ids)
    settings = all_settings(db)
    spend = spend_summary(db, business_ids=ids)
    return {
        "portfolio_actual": {"revenue": tot["revenue"], "expenses": tot["expense"], "profit": round(tot["revenue"] - tot["expense"], 2)},
        "monthly_actuals": months,
        "by_business": per_business,
        "operating_budget": {"monthly_target_usd": settings["monthly_operating_budget_usd"], "ai_month_to_date_usd": spend["month_usd"]},
        "labels": {"actual": "Owner-entered actual revenue and expenses",
                   "pipeline": "ESTIMATE: expected value of open opportunities; never included in actuals",
                   "forecast": "Owner-entered forecast; never included in actuals"},
    }


@router.get("/finance/entries")
def list_entries(ctx: Ctx = Depends(get_ctx), business_id: int | None = None, limit: int = 300):
    stmt = select(FinancialEntry).where(FinancialEntry.business_id.in_(ctx.scope.ids))
    if business_id:
        stmt = stmt.where(FinancialEntry.business_id == business_id)
    return [S.finance_entry(f) for f in ctx.db.execute(stmt.order_by(FinancialEntry.occurred_on.desc()).limit(min(limit, 1000))).scalars()]


@router.post("/finance/entries")
def add_entry(body: FinanceIn, ctx: Ctx = Depends(get_ctx)):
    if not ctx.scope.allows(body.business_id) or ctx.db.get(Business, body.business_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    if body.opportunity_id:
        o = get_scoped(ctx, Opportunity, body.opportunity_id)
        if o.business_id != body.business_id:
            raise HTTPException(status_code=422, detail="Opportunity belongs to another business")
    f = FinancialEntry(entered_by=ctx.actor, **body.model_dump())
    ctx.db.add(f)
    audit(ctx.db, ctx.actor, "finance.entry_added", target_type="financial_entry", business_id=body.business_id,
          detail={"kind": body.kind, "amount": body.amount})
    ctx.db.commit()
    return S.finance_entry(f)


@router.delete("/finance/entries/{fid}")
def delete_entry(fid: int, ctx: Ctx = Depends(get_ctx)):
    f = get_scoped(ctx, FinancialEntry, fid)
    audit(ctx.db, ctx.actor, "finance.entry_deleted", target_type="financial_entry", target_id=f.id, business_id=f.business_id,
          detail={"kind": f.kind, "amount": f.amount})
    ctx.db.delete(f)
    ctx.db.commit()
    return {"ok": True}


@router.get("/finance/forecasts")
def list_forecasts(ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.execute(select(Forecast).where(Forecast.business_id.in_(ctx.scope.ids)).order_by(Forecast.period)).scalars()
    return [{"id": f.id, "business_id": f.business_id, "period": f.period, "revenue": f.revenue, "expenses": f.expenses, "notes": f.notes} for f in rows]


@router.post("/finance/forecasts")
def upsert_forecast(body: ForecastIn, ctx: Ctx = Depends(get_ctx)):
    if not ctx.scope.allows(body.business_id):
        raise HTTPException(status_code=404, detail="Not found")
    f = ctx.db.execute(select(Forecast).where(Forecast.business_id == body.business_id, Forecast.period == body.period)).scalars().first()
    if f is None:
        f = Forecast(**body.model_dump())
        ctx.db.add(f)
    else:
        f.revenue, f.expenses, f.notes = body.revenue, body.expenses, body.notes
    ctx.db.commit()
    return {"ok": True, "id": f.id}


# ----------------------------------------------------------------------------- AI costs


@router.get("/costs/summary")
def costs_summary(ctx: Ctx = Depends(get_ctx)):
    db, ids = ctx.db, ctx.scope.ids
    scope = (AIUsage.business_id.is_(None)) | (AIUsage.business_id.in_(ids))
    month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    by_model = db.execute(select(AIUsage.provider, AIUsage.model, func.count(AIUsage.id), func.sum(AIUsage.input_tokens),
                                 func.sum(AIUsage.output_tokens), func.sum(AIUsage.cost_usd))
                          .where(scope, AIUsage.at >= month, AIUsage.status == "ok").group_by(AIUsage.provider, AIUsage.model)).all()
    by_agent = db.execute(select(AIUsage.agent, func.count(AIUsage.id), func.sum(AIUsage.cost_usd))
                          .where(scope, AIUsage.at >= month, AIUsage.status == "ok").group_by(AIUsage.agent)).all()
    blocked = db.execute(select(func.count(AIUsage.id)).where(scope, AIUsage.at >= month, AIUsage.status == "blocked_budget")).scalar_one()
    cached = db.execute(select(func.count(AIUsage.id)).where(scope, AIUsage.at >= month, AIUsage.cached.is_(True))).scalar_one()
    days = db.execute(select(func.date(AIUsage.at), func.sum(AIUsage.cost_usd)).where(scope, AIUsage.at >= month, AIUsage.status == "ok")
                      .group_by(func.date(AIUsage.at))).all()
    settings = all_settings(db)
    return {
        "spend": spend_summary(db, business_ids=ids),
        "by_model": [{"provider": p, "model": m, "requests": n, "input_tokens": int(i or 0), "output_tokens": int(o or 0),
                      "cost_usd": round(float(c or 0), 4)} for p, m, n, i, o, c in by_model],
        "by_agent": [{"agent": a, "requests": n, "cost_usd": round(float(c or 0), 4)} for a, n, c in by_agent],
        "daily": [{"date": str(d), "cost_usd": round(float(c or 0), 4)} for d, c in days],
        "blocked_by_budget_this_month": blocked,
        "cache_hits_this_month": cached,
        "routes": settings["ai_routes"],
        "label": "Costs computed from provider-reported token counts at list prices; unverified prices are flagged as estimates.",
    }


# ----------------------------------------------------------------------------- settings


EDITABLE = {k for k in DEFAULTS}


@router.get("/settings")
def get_settings_api(ctx: Ctx = Depends(get_ctx)):
    s = get_settings()
    return {"values": all_settings(ctx.db),
            "secrets_configured": {"ANTHROPIC_API_KEY": bool(s.anthropic_api_key), "OPENAI_API_KEY": bool(s.openai_api_key),
                                   "SAM_GOV_API_KEY": bool(s.sam_gov_api_key), "SOCRATA_APP_TOKEN": bool(s.socrata_app_token)},
            "secrets_note": "API keys are configured in the .env file on the host, never through the web UI."}


class SettingsPatch(BaseModel):
    values: dict[str, Any]


@router.patch("/settings")
def patch_settings(body: SettingsPatch, ctx: Ctx = Depends(get_ctx)):
    for k, v in body.values.items():
        if k not in EDITABLE:
            raise HTTPException(status_code=422, detail=f"Unknown setting '{k}'")
        default = DEFAULTS[k]
        if isinstance(default, bool) and not isinstance(v, bool):
            raise HTTPException(status_code=422, detail=f"'{k}' must be true/false")
        if isinstance(default, (int, float)) and not isinstance(default, bool):
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                raise HTTPException(status_code=422, detail=f"'{k}' must be a non-negative number")
        if isinstance(default, dict) and not isinstance(v, dict):
            raise HTTPException(status_code=422, detail=f"'{k}' must be an object")
        if k == "ai_routes":
            for role, r in v.items():
                if not isinstance(r, dict) or r.get("provider") not in ("anthropic", "openai") or not isinstance(r.get("model"), str):
                    raise HTTPException(status_code=422, detail=f"Invalid route for '{role}'")
        set_setting(ctx.db, k, v)
    audit(ctx.db, ctx.actor, "settings.updated", detail=body.values)
    ctx.db.commit()
    return all_settings(ctx.db)


# ----------------------------------------------------------------------------- briefings


@router.get("/briefings")
def list_briefings(ctx: Ctx = Depends(get_ctx), limit: int = 30):
    rows = ctx.db.execute(select(Briefing).where(Briefing.includes_private.is_(ctx.scope.vault_unlocked))
                          .order_by(Briefing.id.desc()).limit(min(limit, 100))).scalars()
    return [S.briefing(b, full=False) for b in rows]


@router.get("/briefings/{bid}")
def get_briefing(bid: int, ctx: Ctx = Depends(get_ctx)):
    b = ctx.db.get(Briefing, bid)
    if b is None or (b.includes_private and not ctx.scope.vault_unlocked):
        raise HTTPException(status_code=404, detail="Not found")
    return S.briefing(b)


@router.post("/briefings/generate")
def generate_briefing(ctx: Ctx = Depends(get_ctx)):
    j = enqueue(ctx.db, "executive_briefing", priority=2, triggered_by=ctx.actor)
    ctx.db.commit()
    return S.job(j)


# ----------------------------------------------------------------------------- search / exports / notifications


@router.get("/search")
def search(ctx: Ctx = Depends(get_ctx), q: str = Query(min_length=2, max_length=200)):
    like = f"%{q}%"
    ids = ctx.scope.ids
    opps = ctx.db.execute(select(Opportunity).where(Opportunity.business_id.in_(ids),
                                                    or_(Opportunity.title.ilike(like), Opportunity.entity_name.ilike(like),
                                                        Opportunity.summary.ilike(like))).limit(25)).scalars()
    contacts = ctx.db.execute(select(Contact).where(Contact.business_id.in_(ids),
                                                    or_(Contact.name.ilike(like), Contact.organization.ilike(like))).limit(15)).scalars()
    tasks = ctx.db.execute(select(Task).where(Task.business_id.in_(ids), Task.title.ilike(like)).limit(15)).scalars()
    biz = ctx.db.execute(select(Business).where(Business.id.in_(ids), or_(Business.name.ilike(like), Business.description.ilike(like)))).scalars()
    return {"opportunities": [S.opportunity(o) for o in opps], "contacts": [S.contact(c) for c in contacts],
            "tasks": [S.task(t) for t in tasks], "businesses": [S.business(b) for b in biz]}


def _csv(rows: list[list[Any]], header: list[str], name: str) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(["'" + str(c) if isinstance(c, str) and c[:1] in ("=", "+", "-", "@") else c for c in r])  # CSV-injection safe
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/exports/opportunities.csv")
def export_opportunities(ctx: Ctx = Depends(get_ctx), business_id: int | None = None):
    stmt = select(Opportunity, Business.name).join(Business).where(Opportunity.business_id.in_(ctx.scope.ids))
    if business_id:
        stmt = stmt.where(Opportunity.business_id == business_id)
    rows = [[o.id, bname, o.title, o.entity_name, o.stage, o.score, o.confidence, o.reported_value, o.expected_value,
             o.estimated_value_basis, o.original_source, o.source_url, o.retrieved_at, o.last_verified_at]
            for o, bname in ctx.db.execute(stmt.order_by(Opportunity.business_id, Opportunity.score.desc())).all()]
    audit(ctx.db, ctx.actor, "export.opportunities", detail={"rows": len(rows), "vault_unlocked": ctx.scope.vault_unlocked}, commit=True)
    return _csv(rows, ["id", "business", "title", "entity", "stage", "score", "confidence", "reported_value",
                       "expected_value_ESTIMATE", "estimate_basis", "source", "source_url", "retrieved_at", "last_verified_at"],
                "opportunities.csv")


@router.get("/exports/financials.csv")
def export_financials(ctx: Ctx = Depends(get_ctx)):
    stmt = select(FinancialEntry, Business.name).join(Business).where(FinancialEntry.business_id.in_(ctx.scope.ids))
    rows = [[f.id, bname, f.kind, f.category, f.amount, f.occurred_on, f.description] for f, bname in ctx.db.execute(stmt).all()]
    audit(ctx.db, ctx.actor, "export.financials", detail={"rows": len(rows)}, commit=True)
    return _csv(rows, ["id", "business", "kind", "category", "amount_ACTUAL", "date", "description"], "financials.csv")


@router.get("/notifications")
def list_notifications(ctx: Ctx = Depends(get_ctx), unread_only: bool = False):
    stmt = select(Notification).where((Notification.business_id.is_(None)) | (Notification.business_id.in_(ctx.scope.ids)))
    if unread_only:
        stmt = stmt.where(Notification.read.is_(False))
    return [S.notification(n) for n in ctx.db.execute(stmt.order_by(Notification.id.desc()).limit(100)).scalars()]


@router.post("/notifications/read-all")
def read_all(ctx: Ctx = Depends(get_ctx)):
    for n in ctx.db.execute(select(Notification).where(Notification.read.is_(False),
                                                       (Notification.business_id.is_(None)) | (Notification.business_id.in_(ctx.scope.ids)))).scalars():
        n.read = True
    ctx.db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------- system


@router.get("/system/health")
def health(ctx: Ctx = Depends(get_ctx)):
    return system_health(ctx)


@router.get("/system/backups")
def backups(ctx: Ctx = Depends(get_ctx)):
    return list_backups()


@router.post("/system/backups")
def make_backup(ctx: Ctx = Depends(get_ctx)):
    p = create_backup("manual")
    audit(ctx.db, ctx.actor, "backup.created", detail={"file": p.name}, commit=True)
    return {"name": p.name}


class RestoreIn(BaseModel):
    name: str = Field(max_length=200, pattern=r"^executive_hub-[\w.-]+\.db$")
    password: str = Field(max_length=256)


@router.post("/system/backups/restore")
def restore(body: RestoreIn, ctx: Ctx = Depends(get_ctx)):
    if not verify_secret(ctx.user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Password required to restore")
    actor = ctx.actor
    ctx.db.close()
    try:
        safety = restore_backup(body.name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    from ..db import session_scope

    with session_scope() as db:
        audit(db, actor, "backup.restored", detail={"file": body.name, "safety_backup": safety.name})
    return {"ok": True, "safety_backup": safety.name, "note": "Restart the app if anything looks stale."}


@router.get("/audit")
def audit_log(ctx: Ctx = Depends(get_ctx), limit: int = 200):
    stmt = select(AuditLog).where((AuditLog.business_id.is_(None)) | (AuditLog.business_id.in_(ctx.scope.ids)))
    return [{"id": a.id, "at": a.at.isoformat(), "actor": a.actor, "action": a.action, "target_type": a.target_type,
             "target_id": a.target_id, "detail": a.detail, "ip": a.ip}
            for a in ctx.db.execute(stmt.order_by(AuditLog.id.desc()).limit(min(limit, 1000))).scalars()]
