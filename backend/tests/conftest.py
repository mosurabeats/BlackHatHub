"""Shared fixtures: isolated SQLite DB per test, migrated with Alembic, seeded; mocked HTTP."""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

os.environ["EXECHUB_ENVIRONMENT"] = "test"
os.environ["EXECHUB_SCHEDULER_ENABLED"] = "false"
for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SAM_GOV_API_KEY", "SOCRATA_APP_TOKEN"):
    os.environ.pop(k, None)

from app import config  # noqa: E402
from app.security import configure_fast_hashing, limiter  # noqa: E402

configure_fast_hashing()

PASSWORD = "Sturdy-Ledger-2026!"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECHUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EXECHUB_STATIC_DIR", str(tmp_path / "nostatic"))
    config.reset_settings_cache()
    limiter.reset()
    from app.main import bootstrap

    bootstrap()
    yield tmp_path
    from app.db import get_engine

    get_engine().dispose()
    config.reset_settings_cache()


@pytest.fixture()
def db(env):
    from app.db import SessionLocal

    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def client(env):
    from app.main import create_app

    app = create_app(start_scheduler=False, run_bootstrap=False)
    with TestClient(app) as c:
        yield c


class Owner:
    def __init__(self, client: TestClient):
        self.c = client
        self.csrf = None

    def setup(self, username="owner", password=PASSWORD):
        r = self.c.post("/api/auth/setup", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]
        return self

    def login(self, username="owner", password=PASSWORD, **kw):
        r = self.c.post("/api/auth/login", json={"username": username, "password": password, **kw})
        if r.status_code == 200:
            self.csrf = r.json()["csrf_token"]
        return r

    def h(self, background=False):
        h = {"X-CSRF-Token": self.csrf or ""}
        if background:
            h["X-Background"] = "1"
        return h

    def get(self, url, **kw):
        return self.c.get(url, headers=self.h(kw.pop("background", False)), **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json or {}, headers=self.h(), **kw)

    def patch(self, url, json=None):
        return self.c.patch(url, json=json or {}, headers=self.h())

    def delete(self, url):
        return self.c.delete(url, headers=self.h())

    def unlock(self, pin="2653"):
        return self.post("/api/vault/unlock", {"pin": pin})


@pytest.fixture()
def owner(client) -> Owner:
    return Owner(client).setup()


# --------------------------------------------------------------------------- HTTP mocking


class MockWeb:
    """Route table for httpx.MockTransport: (substring -> callable(request) or response)."""

    def __init__(self):
        self.routes: list[tuple[str, Callable]] = []
        self.calls: list[str] = []

    def add(self, substring: str, payload=None, status: int = 200, fn: Callable | None = None, text: str | None = None):
        def handler(req: httpx.Request):
            if fn:
                return fn(req)
            if text is not None:
                return httpx.Response(status, text=text)
            return httpx.Response(status, json=payload)

        self.routes.insert(0, (substring, handler))

    def handle(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        self.calls.append(url)
        for sub, h in self.routes:
            if sub in url:
                return h(req)
        return httpx.Response(404, json={"error": "unmocked", "url": url})

    def factory(self):
        from app.research.http import ResearchHttp

        web = self
        return lambda: ResearchHttp(transport=httpx.MockTransport(web.handle), sleep=lambda s: None)


@pytest.fixture()
def web(env, monkeypatch):
    w = MockWeb()
    from app.jobs import handlers

    monkeypatch.setattr(handlers, "HTTP_FACTORY", w.factory())
    return w


def make_private_data(db):
    """Insert private-venture records across every business-scoped table."""
    from app.models import (AIUsage, Approval, Briefing, Business, ComplianceAlert, Contact, FinancialEntry,
                            Notification, Opportunity, Task)

    b = db.query(Business).filter_by(code="B05").one()
    o = Opportunity(business_id=b.id, external_key="secret:1", fingerprint="fp-secret", title="ZZSECRET creator deal",
                    summary="private", entity_name="ZZSECRET LLC", stage="qualified", score=90, expected_value=123456.0,
                    reported_value=999999.0, data={})
    db.add(o)
    db.flush()
    db.add_all([
        Contact(business_id=b.id, name="ZZSECRET Contact"),
        Task(business_id=b.id, title="ZZSECRET task"),
        Notification(business_id=b.id, kind="x", title="ZZSECRET notification"),
        FinancialEntry(business_id=b.id, kind="revenue", amount=77777.0, occurred_on=date.today(), description="ZZSECRET"),
        AIUsage(provider="anthropic", model="claude-haiku-5-5", agent="x", business_id=b.id, cost_usd=5.55, status="ok"),
        ComplianceAlert(business_id=b.id, code="x", title="ZZSECRET alert", dedupe_key="zz"),
        Approval(business_id=b.id, opportunity_id=o.id, action_type="publish_content", proposed_action="ZZSECRET publish",
                 action_hash="h", requested_by="agent:x"),
    ])
    from datetime import datetime, timezone

    db.add(Briefing(period_start=datetime.now(timezone.utc), period_end=datetime.now(timezone.utc), includes_private=True,
                    markdown="ZZSECRET briefing", content={"discovered": {"total": 1}, "approvals_required": [], "rejected": {"total": 0}}))
    db.commit()
    return o


def dumps(r) -> str:
    try:
        return json.dumps(r.json())
    except Exception:
        return r.text
