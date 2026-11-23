"""Authentication, sessions, CSRF and private-vault isolation."""
from datetime import datetime, timedelta, timezone

import pyotp
import pytest

from app.models import AuthSession, VaultConfig
from tests.conftest import PASSWORD, Owner, dumps, make_private_data

PRIVATE_NAMES = ["AI Adult Creator Studio", "Adult Creator Operations SaaS", "Niche Adult Content Studio"]


# ------------------------------------------------------------------ authentication


def test_setup_once_and_password_policy(client):
    r = client.post("/api/auth/setup", json={"username": "owner", "password": "short"})
    assert r.status_code == 422
    Owner(client).setup()
    r = client.post("/api/auth/setup", json={"username": "other", "password": PASSWORD})
    assert r.status_code == 409


def test_unauthenticated_access_denied(client):
    for url in ["/api/dashboard", "/api/businesses", "/api/opportunities", "/api/finance/summary", "/api/exports/opportunities.csv"]:
        assert client.get(url).status_code == 401, url


def test_login_lockout_after_failures(client):
    o = Owner(client).setup()
    o.post("/api/auth/logout")
    for _ in range(5):
        assert o.login(password="wrong-password-123!").status_code == 401
    r = o.login()
    assert r.status_code == 423  # locked even with the right password


def test_csrf_required_for_mutations(owner):
    r = owner.c.post("/api/vault/unlock", json={"pin": "2653"})  # no CSRF header
    assert r.status_code == 403
    r = owner.c.post("/api/vault/unlock", json={"pin": "2653"}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    assert owner.unlock().status_code == 200


def test_logout_revokes_session_and_locks_vault(owner, db):
    owner.unlock()
    assert owner.post("/api/auth/logout").status_code == 200
    assert owner.get("/api/dashboard").status_code == 401
    sess = db.query(AuthSession).one()
    assert sess.revoked and sess.vault_unlocked_at is None


def test_session_idle_expiry(owner, db):
    sess = db.query(AuthSession).one()
    sess.last_seen_at = datetime.now(timezone.utc) - timedelta(hours=5)
    db.commit()
    assert owner.get("/api/dashboard").status_code == 401


def test_session_absolute_expiry(owner, db):
    sess = db.query(AuthSession).one()
    sess.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert owner.get("/api/businesses").status_code == 401


def test_totp_flow(owner):
    secret = owner.post("/api/auth/totp/setup").json()["secret"]
    assert owner.post("/api/auth/totp/enable", {"code": "000000"}).status_code == 400
    assert owner.post("/api/auth/totp/enable", {"code": pyotp.TOTP(secret).now()}).status_code == 200
    owner.post("/api/auth/logout")
    r = owner.login()
    assert r.status_code == 401 and "Authenticator" in r.json()["detail"]
    assert owner.login(totp=pyotp.TOTP(secret).now()).status_code == 200


def test_password_change_signs_out_other_sessions(client):
    a = Owner(client).setup()
    from fastapi.testclient import TestClient

    with TestClient(client.app) as c2:
        b = Owner(c2)
        assert b.login().status_code == 200
        assert a.post("/api/auth/change-password", {"current_password": PASSWORD, "new_password": "Another-Strong-99!"}).status_code == 200
        assert b.get("/api/dashboard").status_code == 401
    assert a.get("/api/dashboard").status_code == 200


def test_passwords_and_pins_are_argon2id_hashed(owner, db):
    from app.models import User

    assert db.query(User).one().password_hash.startswith("$argon2id$")
    assert db.get(VaultConfig, 1).pin_hash.startswith("$argon2id$")
    assert "2653" not in db.get(VaultConfig, 1).pin_hash


# ------------------------------------------------------------------ vault


def test_private_businesses_hidden_until_unlocked(owner):
    names = [b["name"] for b in owner.get("/api/businesses").json()]
    assert len(names) == 4 and not set(PRIVATE_NAMES) & set(names)
    assert owner.get("/api/businesses/creator-ops-saas").status_code == 404
    assert owner.unlock().status_code == 200
    names = [b["name"] for b in owner.get("/api/businesses").json()]
    assert len(names) == 7 and set(PRIVATE_NAMES) <= set(names)


def test_wrong_pin_throttled_and_locked_out(owner):
    for _ in range(5):
        assert owner.unlock("0000").status_code == 401
    assert owner.unlock("2653").status_code == 423


def test_vault_idle_autolock_after_15_minutes(owner, db):
    owner.unlock()
    sess = db.query(AuthSession).one()
    sess.vault_last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    db.commit()
    assert len(owner.get("/api/businesses").json()) == 4
    assert owner.get("/api/vault/status").json()["unlocked"] is False


def test_background_polling_does_not_extend_vault(owner, db):
    owner.unlock()
    sess = db.query(AuthSession).one()
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    sess.vault_last_activity_at = old
    db.commit()
    owner.get("/api/dashboard", background=True)
    db.expire_all()
    assert abs((db.query(AuthSession).one().vault_last_activity_at - old).total_seconds()) < 1
    owner.get("/api/dashboard")
    db.expire_all()
    assert db.query(AuthSession).one().vault_last_activity_at > old + timedelta(minutes=5)


def test_manual_lock(owner):
    owner.unlock()
    owner.post("/api/vault/lock")
    assert len(owner.get("/api/businesses").json()) == 4


def test_vault_unlock_is_per_session(client):
    a = Owner(client).setup()
    a.unlock()
    from fastapi.testclient import TestClient

    with TestClient(client.app) as c2:
        b = Owner(c2)
        b.login()
        assert len(b.get("/api/businesses").json()) == 4


def test_change_pin(owner):
    assert owner.post("/api/vault/change-pin", {"current_pin": "2653", "new_pin": "12", "password": PASSWORD}).status_code == 422
    assert owner.post("/api/vault/change-pin", {"current_pin": "1111", "new_pin": "8642", "password": PASSWORD}).status_code == 401
    assert owner.post("/api/vault/change-pin", {"current_pin": "2653", "new_pin": "8642", "password": PASSWORD}).status_code == 200
    assert owner.unlock("2653").status_code == 401
    assert owner.unlock("8642").status_code == 200
    assert owner.get("/api/auth/status").json()["vault_initial_pin"] is False


LEAK_URLS = [
    "/api/businesses", "/api/dashboard", "/api/opportunities?limit=500", "/api/pipeline/summary", "/api/contacts",
    "/api/tasks", "/api/approvals", "/api/approvals?status=", "/api/notifications", "/api/compliance/alerts",
    "/api/finance/summary", "/api/finance/entries", "/api/costs/summary", "/api/search?q=ZZSECRET", "/api/briefings",
    "/api/exports/opportunities.csv", "/api/exports/financials.csv", "/api/sources", "/api/audit",
]


def test_no_private_leakage_when_locked(owner, db):
    opp = make_private_data(db)
    for url in LEAK_URLS:
        r = owner.get(url)
        assert r.status_code == 200, url
        body = dumps(r)
        assert "ZZSECRET" not in body, url
        for n in PRIVATE_NAMES:
            assert n not in body, (url, n)
    # direct object access is indistinguishable from nonexistent
    assert owner.get(f"/api/opportunities/{opp.id}").status_code == 404
    assert owner.get(f"/api/opportunities/999999").status_code == 404
    assert owner.post(f"/api/opportunities/{opp.id}/transition", {"stage": "lost"}).status_code == 404
    from app.models import Approval, Briefing

    ap = db.query(Approval).one()
    assert owner.get(f"/api/approvals/{ap.id}").status_code == 404
    assert owner.get(f"/api/briefings/{db.query(Briefing).one().id}").status_code == 404


def test_aggregates_exclude_private_when_locked(owner, db):
    make_private_data(db)
    d = owner.get("/api/dashboard").json()
    assert d["financials"]["month"]["revenue"] == 0
    assert d["qualified_pipeline"]["expected_value_estimate"] == 0
    assert d["ai_costs"]["month_usd"] == 0
    assert d["pending_approvals"] == 0 and d["open_tasks"] == 0 and d["regulatory_alerts"] == 0
    assert owner.get("/api/finance/summary").json()["portfolio_actual"]["revenue"] == 0
    owner.unlock()
    d = owner.get("/api/dashboard").json()
    assert d["financials"]["month"]["revenue"] == 77777.0
    assert d["qualified_pipeline"]["expected_value_estimate"] == 123456.0
    assert d["ai_costs"]["month_usd"] == pytest.approx(5.55)
    assert "ZZSECRET" in dumps(owner.get("/api/search?q=ZZSECRET"))


def test_cannot_write_into_private_business_when_locked(owner, db):
    from app.models import Business

    pid = db.query(Business).filter_by(code="B04").one().id
    assert owner.post("/api/finance/entries", {"business_id": pid, "kind": "revenue", "amount": 1, "occurred_on": "2026-01-01"}).status_code == 404
    assert owner.post("/api/tasks", {"business": "ai-creator-studio", "title": "x"}).status_code == 404


def test_errors_do_not_leak_internals(owner):
    r = owner.get("/api/opportunities/not-a-number")
    assert r.status_code == 422 and "Traceback" not in r.text


def test_security_headers(client):
    r = client.get("/api/ping")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_public_internet_clients_rejected():
    from app.main import _ip_allowed

    assert _ip_allowed("192.168.1.20") and _ip_allowed("100.101.102.103") and _ip_allowed("127.0.0.1")
    assert not _ip_allowed("8.8.8.8") and not _ip_allowed("203.0.113.5")
