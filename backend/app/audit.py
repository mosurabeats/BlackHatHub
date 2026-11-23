"""Audit logging with automatic redaction."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog
from .security import redact


def audit(
    db: Session,
    actor: str,
    action: str,
    *,
    target_type: str | None = None,
    target_id: Any = None,
    business_id: int | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        actor=actor[:64],
        action=action[:64],
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        business_id=business_id,
        detail=redact(detail or {}),
        ip=ip,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
