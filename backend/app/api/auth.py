"""Authentication, session management and private-vault endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from ..db import get_db
from ..deps import SESSION_COOKIE, Ctx, client_ip, get_ctx, load_session, lock_vault, vault_is_unlocked
from ..models import AuthSession, User, VaultConfig
from ..security import (
    hash_secret,
    limiter,
    new_token,
    password_problems,
    pin_problems,
    token_digest,
    verify_secret,
)

router = APIRouter(prefix="/api", tags=["auth"])


class SetupIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    totp: str | None = Field(default=None, max_length=10)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class PinIn(BaseModel):
    pin: str = Field(max_length=16)


class PinChangeIn(BaseModel):
    current_pin: str = Field(max_length=16)
    new_pin: str = Field(max_length=16)
    password: str = Field(max_length=256)


class TotpIn(BaseModel):
    code: str = Field(max_length=10)
    password: str | None = Field(default=None, max_length=256)


def _vault_state(sess: AuthSession | None) -> dict:
    s = get_settings()
    if sess is None or not vault_is_unlocked(sess):
        return {"unlocked": False, "idle_timeout_minutes": s.vault_idle_minutes}
    last = sess.vault_last_activity_at or sess.vault_unlocked_at
    return {"unlocked": True, "idle_timeout_minutes": s.vault_idle_minutes,
            "locks_at": (last + timedelta(minutes=s.vault_idle_minutes)).isoformat()}


def _issue_session(db: Session, user: User, request: Request, response: Response) -> AuthSession:
    s = get_settings()
    token = new_token()
    now = datetime.now(timezone.utc)
    sess = AuthSession(token_hash=token_digest(token), csrf_token=new_token(24), user_id=user.id, created_at=now,
                       last_seen_at=now, expires_at=now + timedelta(hours=s.session_hours), ip=client_ip(request),
                       user_agent=(request.headers.get("user-agent") or "")[:255])
    db.add(sess)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict", secure=s.cookie_secure,
                        max_age=s.session_hours * 3600, path="/")
    return sess


@router.get("/auth/status")
def status(request: Request, db: Session = Depends(get_db)):
    users = db.execute(select(func.count(User.id))).scalar_one()
    sess = load_session(request, db)
    if sess and sess.vault_unlocked_at and not vault_is_unlocked(sess):
        lock_vault(sess)
        db.commit()
    vault = db.get(VaultConfig, 1)
    return {
        "setup_required": users == 0,
        "authenticated": sess is not None,
        "user": {"username": sess.user.username, "totp_enabled": sess.user.totp_enabled} if sess else None,
        "csrf_token": sess.csrf_token if sess else None,
        "vault": _vault_state(sess),
        "vault_initial_pin": bool(vault and vault.is_initial_pin) if sess else None,
    }


@router.post("/auth/setup")
def setup(body: SetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if db.execute(select(func.count(User.id))).scalar_one() > 0:
        raise HTTPException(status_code=409, detail="Setup already completed")
    problems = password_problems(body.password, body.username)
    if problems:
        raise HTTPException(status_code=422, detail=" ".join(problems))
    user = User(username=body.username, password_hash=hash_secret(body.password))
    db.add(user)
    db.flush()
    sess = _issue_session(db, user, request, response)
    audit(db, f"user:{user.username}", "auth.setup", ip=client_ip(request))
    db.commit()
    return {"ok": True, "csrf_token": sess.csrf_token}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    ip = client_ip(request) or "?"
    if not limiter.hit(f"login:{ip}", limit=10, window_seconds=300):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    user = db.execute(select(User).where(User.username == body.username)).scalars().first()
    now = datetime.now(timezone.utc)
    generic = HTTPException(status_code=401, detail="Invalid credentials")
    if user is None:
        verify_secret(hash_secret("timing-equalizer"), body.password)
        audit(db, "anonymous", "auth.login_failed", detail={"reason": "unknown_user"}, ip=ip, commit=True)
        raise generic
    if user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=423, detail="Account temporarily locked after repeated failures.")
    ok = verify_secret(user.password_hash, body.password)
    if ok and user.totp_enabled:
        ok = bool(body.totp) and pyotp.TOTP(user.totp_secret).verify(body.totp, valid_window=1)
        if not body.totp:
            raise HTTPException(status_code=401, detail="Authenticator code required")
    if not ok:
        user.failed_logins += 1
        if user.failed_logins >= s.login_max_failures:
            user.locked_until = now + timedelta(minutes=s.login_lockout_minutes)
            user.failed_logins = 0
        audit(db, f"user:{user.username}", "auth.login_failed", ip=ip)
        db.commit()
        raise generic
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    sess = _issue_session(db, user, request, response)
    audit(db, f"user:{user.username}", "auth.login", ip=ip)
    db.commit()
    return {"ok": True, "csrf_token": sess.csrf_token}


@router.post("/auth/logout")
def logout(response: Response, ctx: Ctx = Depends(get_ctx)):
    ctx.session.revoked = True
    lock_vault(ctx.session)  # vault always locks on logout
    audit(ctx.db, ctx.actor, "auth.logout", ip=ctx.ip)
    ctx.db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/auth/change-password")
def change_password(body: PasswordChangeIn, ctx: Ctx = Depends(get_ctx)):
    if not verify_secret(ctx.user.password_hash, body.current_password):
        raise HTTPException(status_code=401, detail="Current password incorrect")
    problems = password_problems(body.new_password, ctx.user.username)
    if problems:
        raise HTTPException(status_code=422, detail=" ".join(problems))
    ctx.user.password_hash = hash_secret(body.new_password)
    for other in ctx.db.execute(select(AuthSession).where(AuthSession.user_id == ctx.user.id, AuthSession.id != ctx.session.id)).scalars():
        other.revoked = True
    audit(ctx.db, ctx.actor, "auth.password_changed", ip=ctx.ip)
    ctx.db.commit()
    return {"ok": True}


@router.post("/auth/totp/setup")
def totp_setup(ctx: Ctx = Depends(get_ctx)):
    secret = pyotp.random_base32()
    ctx.user.totp_secret = secret
    ctx.user.totp_enabled = False
    ctx.db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=ctx.user.username, issuer_name="Executive Hub")
    return {"secret": secret, "otpauth_uri": uri}


@router.post("/auth/totp/enable")
def totp_enable(body: TotpIn, ctx: Ctx = Depends(get_ctx)):
    if not ctx.user.totp_secret or not pyotp.TOTP(ctx.user.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")
    ctx.user.totp_enabled = True
    audit(ctx.db, ctx.actor, "auth.totp_enabled", ip=ctx.ip)
    ctx.db.commit()
    return {"ok": True}


@router.post("/auth/totp/disable")
def totp_disable(body: TotpIn, ctx: Ctx = Depends(get_ctx)):
    if not body.password or not verify_secret(ctx.user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Password required")
    if ctx.user.totp_enabled and not pyotp.TOTP(ctx.user.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")
    ctx.user.totp_enabled = False
    ctx.user.totp_secret = None
    audit(ctx.db, ctx.actor, "auth.totp_disabled", ip=ctx.ip)
    ctx.db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------- vault


@router.get("/vault/status")
def vault_status(ctx: Ctx = Depends(get_ctx)):
    return _vault_state(ctx.session)


@router.post("/vault/unlock")
def vault_unlock(body: PinIn, ctx: Ctx = Depends(get_ctx)):
    s = get_settings()
    vault = ctx.db.get(VaultConfig, 1)
    now = datetime.now(timezone.utc)
    if not limiter.hit(f"vault:{ctx.session.id}", limit=10, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many attempts")
    if vault.locked_until and vault.locked_until > now:
        raise HTTPException(status_code=423, detail="Vault temporarily locked after repeated failures.")
    if not verify_secret(vault.pin_hash, body.pin):
        vault.failed_attempts += 1
        if vault.failed_attempts >= s.vault_max_failures:
            vault.locked_until = now + timedelta(minutes=s.vault_lockout_minutes)
            vault.failed_attempts = 0
        audit(ctx.db, ctx.actor, "vault.unlock_failed", ip=ctx.ip)
        ctx.db.commit()
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    vault.failed_attempts = 0
    vault.locked_until = None
    ctx.session.vault_unlocked_at = now
    ctx.session.vault_last_activity_at = now
    audit(ctx.db, ctx.actor, "vault.unlocked", ip=ctx.ip)
    ctx.db.commit()
    return _vault_state(ctx.session)


@router.post("/vault/lock")
def vault_lock(ctx: Ctx = Depends(get_ctx)):
    lock_vault(ctx.session)
    audit(ctx.db, ctx.actor, "vault.locked", ip=ctx.ip)
    ctx.db.commit()
    return _vault_state(ctx.session)


@router.post("/vault/change-pin")
def vault_change_pin(body: PinChangeIn, ctx: Ctx = Depends(get_ctx)):
    vault = ctx.db.get(VaultConfig, 1)
    if not verify_secret(ctx.user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Password incorrect")
    if not verify_secret(vault.pin_hash, body.current_pin):
        raise HTTPException(status_code=401, detail="Current PIN incorrect")
    problems = pin_problems(body.new_pin)
    if problems:
        raise HTTPException(status_code=422, detail=" ".join(problems))
    vault.pin_hash = hash_secret(body.new_pin)
    vault.is_initial_pin = False
    vault.pin_changed_at = datetime.now(timezone.utc)
    # Changing the PIN locks the vault in every session.
    for sess in ctx.db.execute(select(AuthSession).where(AuthSession.vault_unlocked_at.is_not(None))).scalars():
        lock_vault(sess)
    audit(ctx.db, ctx.actor, "vault.pin_changed", ip=ctx.ip)
    ctx.db.commit()
    return {"ok": True}
