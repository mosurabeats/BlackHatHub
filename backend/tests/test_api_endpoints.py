"""API smoke coverage across workspace endpoints (mocked sources)."""
from datetime import datetime, timezone

from app.models import Business, Job, Opportunity, Source
from tests.test_research import CS_ROWS, TX_MATCH


def _seed_opps(db, web):
    from app.jobs.scheduler import Scheduler, enqueue

    web.add("data.cstx.gov/resource/q83i-2ks8.json", CS_ROWS)
    web.add("data.texas.gov/resource/9cir-efmm.json", TX_MATCH)
    src = db.query(Source).filter_by(key="b07.college_station_unclaimed").one()
    enqueue(db, "research_source", business_id=src.business_id, source_id=src.id)
    db.commit()
    from app.jobs import handlers  # noqa: F401

    Scheduler(worker_threads=1).tick(schedules=False)
    db.expire_all()


def test_workspace_endpoints(owner, db, web):
    _seed_opps(db, web)
    b = owner.get("/api/businesses/asset-recovery").json()
    assert b["stats"]["open_opportunities"] >= 1 and b["stats"]["last_run"]["status"] == "succeeded"
    lst = owner.get("/api/opportunities?business=asset-recovery&q=acme").json()
    assert lst["total"] == 1
    oid = lst["items"][0]["id"]
    d = owner.get(f"/api/opportunities/{oid}").json()
    assert d["evidence"] and d["history"] and d["jurisdiction"]["code"] == "TX" and d["compliance_blockers"]
    assert owner.post(f"/api/opportunities/{oid}/notes", {"text": "Called the city clerk"}).status_code == 200
    assert owner.post(f"/api/opportunities/{oid}/rescore").status_code == 200
    assert owner.post(f"/api/opportunities/{oid}/transition", {"stage": "contacted"}).status_code == 409
    assert owner.post(f"/api/opportunities/{oid}/transition", {"stage": "lost", "reason": "not pursuing"}).status_code == 200
    assert sum(s["count"] for s in owner.get("/api/pipeline/summary").json()) >= 1

    r = owner.post("/api/contacts", {"business": "asset-recovery", "name": "Jane Clerk", "role": "Treasurer office"})
    assert r.status_code == 200 and r.json()["source"] == "manual"
    assert owner.delete(f"/api/contacts/{r.json()['id']}").status_code == 200
    t = owner.post("/api/tasks", {"business": "asset-recovery", "title": "Research TX finder statute", "due_on": "2026-12-01"}).json()
    assert owner.patch(f"/api/tasks/{t['id']}", {"status": "done"}).json()["status"] == "done"

    m = owner.post("/api/opportunities", {"business": "permit-intelligence", "title": "Owner-sourced lead", "entity_name": "X Corp"})
    assert m.status_code == 200 and m.json()["verification_status"] == "unverified"
    assert owner.post("/api/opportunities", {"business": "permit-intelligence", "title": "Owner-sourced lead", "entity_name": "X Corp"}).status_code == 409

    csv = owner.get("/api/exports/opportunities.csv")
    assert csv.status_code == 200 and "expected_value_ESTIMATE" in csv.text and "data.cstx.gov" in csv.text
    assert owner.get("/api/runs").json()[0]["status"] == "succeeded"
    rid = owner.get("/api/runs").json()[0]["id"]
    assert len(owner.get(f"/api/runs/{rid}").json()["events"]) >= 8
    assert "ACME" in owner.get("/api/search?q=acme").text.upper()


def test_sources_jobs_schedules_endpoints(owner, db, web):
    srcs = owner.get("/api/sources").json()
    assert not any(s["status"] == "proposed" for s in srcs)  # private-venture proposals hidden while locked
    proposed = next(s for s in srcs if s["key"] == "b07.discovery")
    r = owner.post(f"/api/sources/{proposed['id']}/run")
    assert r.status_code == 200 and r.json()["status"] == "queued"
    jid = r.json()["id"]
    assert owner.post(f"/api/jobs/{jid}/cancel").json()["status"] == "cancelled"
    assert owner.post(f"/api/jobs/{jid}/retry").json()["status"] == "queued"
    # a discovered dataset cannot be enabled before its field mapping is configured
    db.add(Source(key="socrata:x:y", business_id=proposed["business_id"], name="Proposed", adapter="socrata_dataset",
                  config={"domain": "x", "dataset": "y", "fields": {}}, enabled=False, status="proposed"))
    db.commit()
    sid = db.query(Source).filter_by(key="socrata:x:y").one().id
    assert owner.patch(f"/api/sources/{sid}", {"enabled": True}).status_code == 422
    assert owner.patch(f"/api/sources/{sid}", {"fields": {"owner": "name"}, "jurisdiction": "ny"}).status_code == 200
    assert owner.patch(f"/api/sources/{sid}", {"enabled": True}).json()["status"] == "active"
    assert owner.post("/api/sources/rss", {"business_id": proposed["business_id"], "name": "Feed", "url": "https://example.com/rss"}).status_code == 200
    sch = owner.get("/api/schedules").json()
    assert {s["job_type"] for s in sch} >= {"research_cycle", "jurisdiction_portal_check", "backup"}
    assert owner.patch(f"/api/schedules/{sch[0]['id']}", {"interval_minutes": 5}).status_code == 422
    assert owner.patch(f"/api/schedules/{sch[0]['id']}", {"interval_minutes": 360}).json()["interval_minutes"] == 360
    assert owner.post(f"/api/schedules/{sch[0]['id']}/run-now").status_code == 200
    assert owner.post("/api/jobs/research-cycle").json()["job_type"] == "research_cycle"
    assert owner.get("/api/jobs").status_code == 200
    h = owner.get("/api/system/health").json()
    assert h["scheduler"]["alive"] is False and h["ai"]["anthropic_configured"] is False


def test_portal_check_and_briefing_jobs(owner, db, web):
    from app.jobs import handlers  # noqa: F401
    from app.jobs.scheduler import Scheduler

    web.add("https://", text="<html><body>Unclaimed property program</body></html>")
    web.add("claimittexas", {"x": 1}, status=403)
    owner.post("/api/jurisdictions/check-portals")
    owner.post("/api/briefings/generate")
    Scheduler(worker_threads=1).tick(schedules=False)
    db.expire_all()
    assert owner.get("/api/jurisdictions/TX").json()["portal_status"] == "blocked"  # 403 recorded as bot-blocked
    j = owner.get("/api/jurisdictions/AL").json()
    assert j["portal_status"] == "reachable" and j["portal_last_checked_at"] and j["portal_http_status"] == 200
    assert all(x["portal_status"] != "unchecked" for x in owner.get("/api/jurisdictions").json())
    briefs = owner.get("/api/briefings").json()
    assert len(briefs) == 1  # only the public variant while locked
    full = owner.get(f"/api/briefings/{briefs[0]['id']}").json()
    assert "Requires your approval" in full["markdown"]
    owner.unlock()
    assert len(owner.get("/api/briefings").json()) == 1 and owner.get("/api/briefings").json()[0]["includes_private"]
    assert owner.post("/api/system/backups").status_code == 200 and owner.get("/api/system/backups").json()
    assert owner.get("/api/audit").json()
    assert owner.get("/api/costs/summary").json()["spend"]["month_usd"] == 0
