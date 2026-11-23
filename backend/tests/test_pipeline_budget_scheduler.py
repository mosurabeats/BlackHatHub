"""Pipeline transitions, approval enforcement, budgets, scheduler reliability, migrations, backup/restore."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Approval, Business, Job, Jurisdiction, Opportunity, Schedule
from app.pipeline import (ApprovalError, TransitionError, action_hash, assert_authorized, decide_approval,
                          mark_executed, request_approval, transition)


def _opp(db, code="B01", stage="qualified", **kw):
    b = db.query(Business).filter_by(code=code).one()
    o = Opportunity(business_id=b.id, external_key=f"t:{datetime.now().timestamp()}", fingerprint=str(datetime.now().timestamp()),
                    title="Test permit", stage=stage, data={}, **kw)
    db.add(o)
    db.commit()
    return o


def _request(db, o, **kw):
    return request_approval(db, business_id=o.business_id, opportunity=o, action_type="contact_prospect",
                            proposed_action="Send one intro letter to BuildCo", justification="High score",
                            evidence_summary="permit record", expected_benefit="lead", risks="none significant",
                            estimated_cost_usd=1.0, requested_by="agent:pipeline_manager", payload={"opportunity_id": o.id}, **kw)


# ------------------------------------------------------------------ pipeline transitions


def test_agents_limited_to_internal_stages(db):
    o = _opp(db, stage="researching")
    transition(db, o, "verified", "agent:research_analyst")
    with pytest.raises(TransitionError):
        transition(db, o, "contacted", "agent:pipeline_manager")
    with pytest.raises(TransitionError):
        transition(db, o, "outreach_approved", "agent:pipeline_manager")


def test_owner_cannot_skip_approval(db):
    o = _opp(db)
    with pytest.raises(TransitionError):
        transition(db, o, "contacted", "user:owner")
    with pytest.raises(TransitionError):
        transition(db, o, "outreach_approved", "user:owner")


def test_approval_flow_single_specific_action(db):
    o = _opp(db)
    ap = _request(db, o)
    assert o.stage == "awaiting_approval"
    with pytest.raises(ApprovalError):
        _request(db, o)  # one pending request at a time
    with pytest.raises(ApprovalError):
        decide_approval(db, ap, approve=True, actor="agent:x", confirm_hash=ap.action_hash)  # agents can't approve
    with pytest.raises(ApprovalError):
        decide_approval(db, ap, approve=True, actor="user:owner", confirm_hash="wrong")
    decide_approval(db, ap, approve=True, actor="user:owner", confirm_hash=ap.action_hash)
    assert o.stage == "outreach_approved" and ap.status == "approved"
    # authorization covers exactly this action
    assert_authorized(db, ap.id, "contact_prospect", {"opportunity_id": o.id})
    with pytest.raises(ApprovalError):
        assert_authorized(db, ap.id, "initiate_payment", {"opportunity_id": o.id})
    with pytest.raises(ApprovalError):
        assert_authorized(db, ap.id, "contact_prospect", {"opportunity_id": o.id, "amount": 1000})
    transition(db, o, "contacted", "user:owner", "letter sent")
    mark_executed(db, ap, actor="user:owner", result="Letter mailed")
    with pytest.raises(ApprovalError):
        mark_executed(db, ap, actor="user:owner", result="again")  # consumed
    with pytest.raises(ApprovalError):
        assert_authorized(db, ap.id, "contact_prospect", {"opportunity_id": o.id})
    stages = [h.to_stage for h in o.history if h.event == "stage_change"]
    assert stages[-3:] == ["awaiting_approval", "outreach_approved", "contacted"]


def test_tampered_approval_cannot_execute(db):
    o = _opp(db)
    ap = _request(db, o)
    decide_approval(db, ap, approve=True, actor="user:owner", confirm_hash=ap.action_hash)
    ap.proposed_action = "Send letter AND wire $10,000"
    with pytest.raises(ApprovalError):
        mark_executed(db, ap, actor="user:owner", result="x")


def test_expired_approval_cannot_be_approved(db):
    o = _opp(db)
    ap = _request(db, o)
    ap.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    with pytest.raises(ApprovalError):
        decide_approval(db, ap, approve=True, actor="user:owner", confirm_hash=ap.action_hash)
    assert ap.status == "expired"


def test_api_approval_blocked_by_compliance(owner, db):
    o = _opp(db, code="B07", category="unclaimed_property", jurisdiction_code="TX")
    r = owner.post(f"/api/opportunities/{o.id}/request-approval", {
        "action_type": "contact_prospect", "proposed_action": "Write to claimant", "justification": "value",
        "expected_benefit": "fee", "risks": "regulatory"})
    assert r.status_code == 200 and r.json()["compliance_blockers"]
    r = owner.post(f"/api/approvals/{r.json()['id']}/approve", {"confirm_hash": r.json()["action_hash"]})
    assert r.status_code == 409 and "compliance" in r.json()["detail"]


def test_api_approval_requires_all_fields(owner, db):
    o = _opp(db)
    r = owner.post(f"/api/opportunities/{o.id}/request-approval", {"action_type": "contact_prospect", "proposed_action": "x"})
    assert r.status_code == 422


def test_jurisdiction_verification_requires_citation_and_clearing_requires_verification(owner, db):
    assert len(owner.get("/api/jurisdictions").json()) == 51
    assert all(j["compliance_review_status"] == "unverified_seed" for j in owner.get("/api/jurisdictions").json())
    assert owner.patch("/api/jurisdictions/TX", {"operating_status": "cleared"}).status_code == 422
    assert owner.patch("/api/jurisdictions/TX", {"compliance_review_status": "verified"}).status_code == 422
    r = owner.patch("/api/jurisdictions/TX", {"compliance_review_status": "verified", "max_fee_percent": 10,
                                              "add_citations": [{"title": "Tex. Prop. Code (official)", "url": "https://statutes.capitol.texas.gov/"}]})
    assert r.status_code == 200 and r.json()["last_verified_at"]
    assert owner.patch("/api/jurisdictions/TX", {"operating_status": "cleared"}).status_code == 200


def test_scoring_uses_verified_fee_cap(db):
    from app.agents.scoring import score_asset_recovery
    from app.app_settings import all_settings

    o = _opp(db, code="B07", category="unclaimed_property", reported_value=50000.0, jurisdiction_code="TX",
             verification_status="source_record_official")
    jur = db.get(Jurisdiction, "TX")
    unverified = score_asset_recovery(o, jur, all_settings(db))
    assert "ASSUMED" in unverified.estimated_value_basis
    jur.compliance_review_status, jur.max_fee_percent = "verified", 5.0
    verified = score_asset_recovery(o, jur, all_settings(db))
    assert "verified TX fee cap 5.0%" in verified.estimated_value_basis
    assert verified.estimated_value < 50000 * 0.05


# ------------------------------------------------------------------ budget


def test_budget_hard_limit_blocks_ai_calls(db, monkeypatch):
    from app.ai import client as ai
    from app.ai.budget import BudgetExceeded
    from app.app_settings import set_setting
    from app.models import AIUsage

    calls = []
    monkeypatch.setitem(ai.PROVIDERS, "anthropic", lambda m, s, u, sc, mt: (calls.append(1), ('{"a": 1}', 1000, 100, m))[1])
    set_setting(db, "ai_daily_budget_usd", 0.0001)
    db.commit()
    with pytest.raises(BudgetExceeded):
        ai.complete_json(db, agent="t", purpose="t", role="analysis", instructions="x", documents=[{"text": "y"}],
                         schema={"type": "object"}, max_tokens=500)
    assert not calls and db.query(AIUsage).filter_by(status="blocked_budget").count() == 1


def test_budget_per_job_and_cache(db, monkeypatch):
    from app.ai import client as ai
    from app.ai.budget import BudgetExceeded
    from app.app_settings import set_setting
    from app.models import AIUsage

    monkeypatch.setitem(ai.PROVIDERS, "anthropic", lambda m, s, u, sc, mt: ('{"ok": true}', 1000, 200, m))
    job = Job(job_type="x")
    db.add(job)
    db.commit()
    set_setting(db, "ai_job_budget_usd", 0.03)
    db.commit()
    kw = dict(agent="t", purpose="t", role="analysis", schema={"type": "object"}, max_tokens=200, job_id=job.id)
    r1 = ai.complete_json(db, instructions="a", documents=[{"text": "1"}], **kw)
    assert r1.cost_usd == pytest.approx(1000 / 1e6 * 4 + 200 / 1e6 * 20)
    r2 = ai.complete_json(db, instructions="a", documents=[{"text": "1"}], **kw)  # cached: free
    assert r2.cached and r2.cost_usd == 0
    ai.complete_json(db, instructions="b", documents=[{"text": "2"}], **kw)
    with pytest.raises(BudgetExceeded):
        for i in range(10):
            ai.complete_json(db, instructions=f"c{i}", documents=[{"text": "3"}], **kw)
    assert db.query(AIUsage).filter_by(cached=True).count() == 1


def test_soft_limit_warns_instead_of_blocking(db):
    from app.ai.budget import check_budget
    from app.app_settings import set_setting

    set_setting(db, "ai_hard_limit", False)
    set_setting(db, "ai_daily_budget_usd", 0.0)
    assert check_budget(db, 1.0)


def test_ai_unavailable_without_key(db):
    from app.ai import client as ai

    with pytest.raises(ai.AIUnavailable):
        ai.complete_json(db, agent="t", purpose="t", role="analysis", instructions="x", documents=[], schema={"type": "object"})


# ------------------------------------------------------------------ scheduler


@pytest.fixture()
def sched(env):
    from app.jobs import handlers  # noqa: F401
    from app.jobs.scheduler import Scheduler

    return Scheduler(worker_threads=1)


def _register(name, fn):
    from app.jobs.scheduler import HANDLERS

    HANDLERS[name] = fn


def test_schedule_enqueues_and_missed_runs_coalesce(db, sched):
    _register("t_ok", lambda ctx: {"ok": 1})
    s = Schedule(key="t", name="t", job_type="t_ok", interval_minutes=60, next_run_at=datetime.now(timezone.utc) - timedelta(hours=5, minutes=1))
    db.add(s)
    db.commit()
    jobs = sched.enqueue_due(db)
    db.commit()
    assert len([j for j in jobs if j.job_type == "t_ok"]) == 1  # one catch-up run, not five
    db.refresh(s)
    assert s.missed_runs == 5 and s.next_run_at > datetime.now(timezone.utc)
    assert db.query(Job).filter_by(job_type="t_ok").one().triggered_by == "schedule:catch_up"


def test_retry_with_backoff_then_fail(db, sched):
    from app.jobs.scheduler import enqueue

    def boom(ctx):
        raise RuntimeError("transient")

    _register("t_boom", boom)
    j = enqueue(db, "t_boom", max_attempts=2)
    db.commit()
    assert sched.tick(schedules=False) == ["retry_wait"]
    db.refresh(j)
    assert j.next_attempt_at > datetime.now(timezone.utc) + timedelta(seconds=30)
    j.next_attempt_at = datetime.now(timezone.utc)
    db.commit()
    assert sched.tick(schedules=False) == ["failed"]
    db.refresh(j)
    assert j.status == "failed" and "transient" in j.error and j.attempts == 2


def test_non_retryable_fails_immediately(db, sched):
    from app.jobs.scheduler import NonRetryable, enqueue

    def bad(ctx):
        raise NonRetryable("config error")

    _register("t_bad", bad)
    enqueue(db, "t_bad")
    db.commit()
    assert sched.tick(schedules=False) == ["failed"]


def test_cancel_queued_and_running(db, sched):
    from app.jobs.scheduler import cancel, enqueue

    j = enqueue(db, "t_ok")
    cancel(db, j)
    db.commit()
    assert j.status == "cancelled" and sched.tick(schedules=False) == []

    def long(ctx):
        from app.models import Job as J

        ctx.db.query(J).filter_by(id=ctx.job.id).update({"cancel_requested": True})
        ctx.db.commit()
        ctx.check_cancel()
        return {"should": "not reach"}

    _register("t_long", long)
    j2 = enqueue(db, "t_long")
    db.commit()
    assert sched.tick(schedules=False) == ["cancelled"]


def test_restart_recovery_requeues_running_jobs(db, sched):
    _register("t_ok", lambda ctx: {"ok": 1})
    j = Job(job_type="t_ok", status="running", attempts=1, worker_id="dead-worker", started_at=datetime.now(timezone.utc))
    db.add(j)
    db.commit()
    assert sched.recover_on_startup() == 1
    db.refresh(j)
    assert j.status == "queued" and j.recovered
    assert sched.tick(schedules=False) == ["succeeded"]


def test_stuck_job_heartbeat_recovery(db, sched):
    j = Job(job_type="t_ok", status="running", attempts=1, heartbeat_at=datetime.now(timezone.utc) - timedelta(hours=2))
    db.add(j)
    db.commit()
    assert sched.recover_stuck(db) == 1


def test_job_success_only_when_handler_returns(db, sched):
    from app.jobs.scheduler import enqueue
    from app.models import ResearchRun

    def partial_then_crash(ctx):
        ctx.db.add(ResearchRun(business_id=1, status="running"))
        ctx.db.flush()
        raise ValueError("crashed midway")

    _register("t_crash", partial_then_crash)
    enqueue(db, "t_crash", max_attempts=1)
    db.commit()
    assert sched.tick(schedules=False) == ["failed"]
    assert db.query(ResearchRun).count() == 0  # partial work rolled back


def test_full_cycle_with_mocked_sources(db, web, sched):
    """Research Director -> research jobs -> maintenance -> briefing, all succeed with empty/mocked sources."""
    from app.jobs.scheduler import enqueue

    web.add("resource", [])
    web.add("api.usaspending.gov", {"results": [], "page_metadata": {"hasNext": False}})
    enqueue(db, "research_cycle")
    db.commit()
    for _ in range(10):
        sched.tick(schedules=False)
        db.query(Job).filter(Job.status == "queued").update({"next_attempt_at": datetime.now(timezone.utc)})
        db.commit()
    statuses = {j.job_type: j.status for j in db.query(Job)}
    assert statuses["research_cycle"] == "succeeded"
    assert statuses["executive_briefing"] == "succeeded" and statuses["pipeline_maintenance"] == "succeeded"
    from app.models import Briefing

    briefs = db.query(Briefing).all()
    assert {b.includes_private for b in briefs} == {True, False}
    assert all("No new opportunities" in b.markdown for b in briefs)  # never fabricated activity


# ------------------------------------------------------------------ migrations / backup


def test_migrations_match_models(env):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db import Base, get_engine

    with get_engine().connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_migration_downgrade_and_upgrade(env, tmp_path):
    from sqlalchemy import create_engine, inspect

    from app.migrate import downgrade, upgrade

    url = f"sqlite:///{tmp_path}/m.db"
    upgrade(url)
    assert "opportunities" in inspect(create_engine(url)).get_table_names()
    downgrade(url)
    assert "opportunities" not in inspect(create_engine(url)).get_table_names()
    upgrade(url)


def test_backup_and_restore_roundtrip(owner, db):
    from app.backup import create_backup, list_backups, restore_backup

    o = _opp(db)
    b = create_backup("test")
    db.delete(o)
    db.commit()
    db.close()
    assert len(list_backups()) == 1
    safety = restore_backup(b.name)
    from app.db import SessionLocal

    with SessionLocal() as s2:
        assert s2.get(Opportunity, o.id) is not None
    assert safety.exists()


def test_restore_rejects_path_traversal(owner):
    r = owner.post("/api/system/backups/restore", {"name": "../../etc/passwd", "password": "x"})
    assert r.status_code == 422


def test_settings_validation(owner):
    assert owner.patch("/api/settings", {"values": {"nope": 1}}).status_code == 422
    assert owner.patch("/api/settings", {"values": {"ai_daily_budget_usd": -5}}).status_code == 422
    assert owner.patch("/api/settings", {"values": {"ai_routes": {"analysis": {"provider": "evil", "model": "x"}}}}).status_code == 422
    assert owner.patch("/api/settings", {"values": {"ai_daily_budget_usd": 2.5}}).json()["ai_daily_budget_usd"] == 2.5
    s = owner.get("/api/settings").json()
    assert "ANTHROPIC_API_KEY" in s["secrets_configured"] and "sk-" not in str(s)


def test_redaction():
    from app.security import redact

    out = redact({"password": "x", "nested": {"api_key": "y"}, "text": "key sk-ant-abcdefghijklmnop"})
    assert out["password"] == "[REDACTED]" and out["nested"]["api_key"] == "[REDACTED]" and "sk-ant" not in out["text"]


def test_finance_actuals_never_include_estimates(owner, db):
    _opp(db, expected_value=50000.0, estimated_value=60000.0)
    b = db.query(Business).filter_by(code="B01").one()
    owner.post("/api/finance/entries", {"business_id": b.id, "kind": "revenue", "amount": 100, "occurred_on": "2026-11-01"})
    s = owner.get("/api/finance/summary").json()
    assert s["portfolio_actual"]["revenue"] == 100
    row = next(x for x in s["by_business"] if x["business_id"] == b.id)
    assert row["actual"]["revenue"] == 100 and row["pipeline_expected_value_estimate"] == 50000.0
