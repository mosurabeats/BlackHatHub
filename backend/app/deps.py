"""Request dependencies: authentication, CSRF, vault state and privacy scope."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AuthSession, User
from .privacy import Scope, build_scope
from .security import constant_time_eq, token_digest

SESSION_COOKIE = "exechub_session"
CSRF_HEADER = "X-CSRF-Token"
BACKGROUND_HEADER = "X-Background"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Ctx:
    db: Session
    user: User
    session: AuthSession
    scope: Scope
    ip: str | None

    @property
    def actor(self) -> str:
        return f"user:{self.user.username}"


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def vault_is_unlocked(sess: AuthSession, now: datetime | None = None) -> bool:
    if sess.vault_unlocked_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    last = sess.vault_last_activity_at or sess.vault_unlocked_at
    return now - last <= timedelta(minutes=get_settings().vault_idle_minutes)


def lock_vault(sess: AuthSession) -> None:
    sess.vault_unlocked_at = None
    sess.vault_last_activity_at = None


def load_session(request: Request, db: Session) -> AuthSession | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    sess = db.execute(select(AuthSession).where(AuthSession.token_hash == token_digest(token))).scalars().first()
    if sess is None or sess.revoked:
        return None
    now = datetime.now(timezone.utc)
    idle = timedelta(minutes=get_settings().session_idle_minutes)
    if sess.expires_at < now or now - sess.last_seen_at > idle:
        sess.revoked = True
        lock_vault(sess)
        db.commit()
        return None
    if not sess.user.is_active:
        return None
    return sess


def get_ctx(request: Request, db: Session = Depends(get_db)) -> Ctx:
    sess = load_session(request, db)
    if sess is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not constant_time_eq(sent, sess.csrf_token):
            raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
    now = datetime.now(timezone.utc)
    background = request.headers.get(BACKGROUND_HEADER) == "1"
    unlocked = vault_is_unlocked(sess, now)
    if sess.vault_unlocked_at is not None and not unlocked:
        lock_vault(sess)  # idle timeout
    if not background:
        sess.last_seen_at = now
        if unlocked:
            sess.vault_last_activity_at = now
    db.commit()
    return Ctx(db=db, user=sess.user, session=sess, scope=build_scope(db, unlocked), ip=client_ip(request))


def require_scope_business(ctx: Ctx, business_id: int | None) -> None:
    """404 (not 403) so locked private businesses are indistinguishable from nonexistent ones."""
    if business_id is not None and not ctx.scope.allows(business_id):
        raise HTTPException(status_code=404, detail="Not found")


def get_scoped(ctx: Ctx, model, obj_id):
    obj = ctx.db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Not found")
    require_scope_business(ctx, getattr(obj, "business_id", None))
    return obj
