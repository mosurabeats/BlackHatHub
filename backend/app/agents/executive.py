"""Executive Analyst: briefings grounded strictly in stored research.

The briefing content is assembled deterministically from database records.
An optional AI summary may be added; it receives only those facts and is
labelled as an AI-written summary. Two variants are produced per cycle: a
public one, and one that includes private-vault businesses (only shown when
the vault is unlocked).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai import client as ai
from ..ai.budget import BudgetExceeded
from ..app_settings import get_setting
from ..models import (
    STAGE_LABELS,
    Approval,
    Briefing,
    Business,
    ComplianceAlert,
    Job,
    Opportunity,
    OpportunityHistory,
    ResearchRun,
    Schedule,
    Source,
)
from ..privacy import system_scope

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"headline": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}},
    "required": ["headline", "bullets"],
    "additionalProperties": False,
}


def _money(v: float | None) -> str:
    return "n/a" if v is None else f"${v:,.0f}"


def build_content(db: Session, ids: list[int], start: datetime, end: datetime) -> dict[str, Any]:
    biz = {b.id: b for b in db.execute(select(Business).where(Business.id.in_(ids))).scalars()}
    in_scope = Opportunity.business_id.in_(ids)
    new_opps = db.execute(select(Opportunity).where(in_scope, Opportunity.created_at >= start, Opportunity.created_at < end)).scalars().all()
    discovered_by_biz: dict[str, int] = {}
    for o in new_opps:
        discovered_by_biz[biz[o.business_id].name] = discovered_by_biz.get(biz[o.business_id].name, 0) + 1
    strongest = db.execute(select(Opportunity).where(in_scope, Opportunity.stage.in_(["qualified", "awaiting_approval", "outreach_approved"]))
                           .order_by(Opportunity.score.desc()).limit(10)).scalars().all()
    hist = db.execute(select(OpportunityHistory, Opportunity).join(Opportunity)
                      .where(in_scope, OpportunityHistory.at >= start, OpportunityHistory.at < end)).all()
    changes = [{"opportunity_id": o.id, "title": o.title, "event": h.event,
                "detail": h.reason or "", "from": h.from_stage, "to": h.to_stage, "changes": h.changes}
               for h, o in hist if h.event in ("updated", "rescored") or (h.event == "stage_change" and h.to_stage not in ("discovered", "researching"))]
    rejected = [{"opportunity_id": o.id, "title": o.title, "business": biz[o.business_id].name, "reason": h.reason}
                for h, o in hist if h.event == "stage_change" and h.to_stage == "lost"]
    alerts = db.execute(select(ComplianceAlert).where(ComplianceAlert.business_id.in_(ids), ComplianceAlert.created_at >= start)).scalars().all()
    open_alerts = db.execute(select(func.count(ComplianceAlert.id)).where(ComplianceAlert.business_id.in_(ids), ComplianceAlert.status == "open")).scalar_one()
    approvals = db.execute(select(Approval).where(Approval.business_id.in_(ids), Approval.status == "pending")).scalars().all()
    runs = db.execute(select(ResearchRun).where(ResearchRun.business_id.in_(ids), ResearchRun.started_at >= start, ResearchRun.started_at < end)).scalars().all()
    failures = []
    for r in runs:
        if r.status in ("failed", "partial"):
            src = db.get(Source, r.source_id) if r.source_id else None
            failures.append({"source": src.name if src else "?", "status": r.status, "limitations": r.limitations or [r.error]})
    planned = db.execute(select(Schedule).where(Schedule.enabled.is_(True),
                                                (Schedule.business_id.is_(None)) | (Schedule.business_id.in_(ids)))
                         .order_by(Schedule.next_run_at).limit(8)).scalars().all()
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "discovered": {"total": len(new_opps), "by_business": discovered_by_biz},
        "strongest": [{"id": o.id, "title": o.title, "business": biz[o.business_id].name, "score": o.score,
                       "stage": STAGE_LABELS[o.stage], "reported_value": o.reported_value, "expected_value": o.expected_value,
                       "basis": o.estimated_value_basis, "action": o.recommended_action, "source_url": o.source_url} for o in strongest],
        "changes": changes[:50],
        "rejected": {"total": len(rejected), "items": rejected[:25]},
        "regulatory": {"new_alerts": [{"title": a.title, "severity": a.severity, "detail": a.detail} for a in alerts[:25]],
                       "open_alerts": open_alerts},
        "research_runs": {"total": len(runs), "succeeded": sum(r.status == "succeeded" for r in runs),
                          "partial": sum(r.status == "partial" for r in runs), "failed": sum(r.status == "failed" for r in runs),
                          "limitations": failures[:20]},
        "planned_next": [{"name": s.name, "next_run_at": s.next_run_at.isoformat()} for s in planned],
        "approvals_required": [{"id": a.id, "action_type": a.action_type, "proposed_action": a.proposed_action,
                                "business": biz[a.business_id].name} for a in approvals],
    }


def to_markdown(c: dict[str, Any], includes_private: bool) -> str:
    L = [f"# Executive Briefing", f"_Period {c['period']['start'][:16]} -> {c['period']['end'][:16]} UTC"
         + (" | includes private ventures_" if includes_private else "_"), ""]
    L.append("## What the system discovered")
    if c["discovered"]["total"]:
        L.append(f"{c['discovered']['total']} new opportunities: " + ", ".join(f"{k}: {v}" for k, v in c["discovered"]["by_business"].items()))
    else:
        L.append("No new opportunities were discovered in this period.")
    rr = c["research_runs"]
    L.append(f"Research runs: {rr['total']} ({rr['succeeded']} succeeded, {rr['partial']} partial, {rr['failed']} failed).")
    L += ["", "## Strongest opportunities"]
    if c["strongest"]:
        for o in c["strongest"]:
            L.append(f"- **{o['title']}** ({o['business']}) - score {o['score']:.0f}, {o['stage']}; reported {_money(o['reported_value'])}, "
                     f"expected value (estimate) {_money(o['expected_value'])}. Next: {o['action']}")
    else:
        L.append("No opportunities are currently qualified.")
    L += ["", "## What changed"]
    L += [f"- {x['title']}: {x['event']} {x.get('detail') or ''}".rstrip() for x in c["changes"][:15]] or ["No tracked changes."]
    L += ["", "## Rejected leads", f"{c['rejected']['total']} rejected."]
    L += [f"- {x['title']}: {x['reason']}" for x in c["rejected"]["items"][:10]]
    L += ["", "## Legal / regulatory", f"{c['regulatory']['open_alerts']} open compliance alerts."]
    L += [f"- [{a['severity']}] {a['title']}" for a in c["regulatory"]["new_alerts"][:10]]
    if rr["limitations"]:
        L += ["", "## Limitations encountered"]
        L += [f"- {x['source']}: {'; '.join(str(i) for i in x['limitations'] if i)}" for x in rr["limitations"]]
    L += ["", "## Research planned next"] + [f"- {p['name']} at {p['next_run_at'][:16]} UTC" for p in c["planned_next"]]
    L += ["", "## Requires your approval"]
    L += [f"- #{a['id']} ({a['business']}): {a['proposed_action']}" for a in c["approvals_required"]] or ["Nothing pending."]
    return "\n".join(L)


def generate(db: Session, *, job_id: int | None = None, now: datetime | None = None) -> list[Briefing]:
    now = now or datetime.now(timezone.utc)
    out = []
    for include_private in (False, True):
        prev = db.execute(select(Briefing).where(Briefing.includes_private.is_(include_private))
                          .order_by(Briefing.created_at.desc())).scalars().first()
        start = prev.period_end if prev else now - timedelta(days=1)
        scope = system_scope(db, include_private)
        content = build_content(db, scope.ids, start, now)
        b = Briefing(period_start=start, period_end=now, includes_private=include_private, job_id=job_id, content=content,
                     markdown=to_markdown(content, include_private))
        if get_setting(db, "ai_briefing_summary_enabled"):
            try:
                provider, _ = ai.route(db, "briefing")
                if ai.provider_available(provider) and content["discovered"]["total"] + len(content["changes"]) + len(content["approvals_required"]) > 0:
                    import json

                    res = ai.complete_json(
                        db, agent="executive_analyst", purpose="briefing summary", role="briefing",
                        instructions="Write a concise executive summary (headline + up to 6 bullets) using ONLY the facts in the "
                                     "document. Label estimates as estimates. Do not invent activity.",
                        documents=[{"source": "executive_hub_database", "text": json.dumps(content, default=str)[:30000]}],
                        schema=SUMMARY_SCHEMA, job_id=job_id, max_tokens=1200,
                        # attribute private-inclusive cost to a private business so it is hidden while locked
                        business_id=(min(scope.private_ids) if include_private and scope.private_ids else None),
                    )
                    b.ai_summary = res.data["headline"] + "\n" + "\n".join(f"- {x}" for x in res.data["bullets"])
                    b.generated_by = f"deterministic+ai:{res.model}"
            except (BudgetExceeded, ai.AIUnavailable) as exc:
                b.content = {**content, "ai_summary_unavailable": str(exc)}
        db.add(b)
        out.append(b)
    db.flush()
    return out
