"""Central private-vault scoping.

Every query that touches business-scoped data MUST pass through
``visible_business_ids`` (or ``Scope``). Private businesses (04, 05, 06) are
excluded unless the current authenticated session has an unexpired vault
unlock. This is enforced server-side; the frontend merely reflects it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Business


@dataclass(frozen=True)
class Scope:
    vault_unlocked: bool
    business_ids: frozenset[int] = field(default_factory=frozenset)
    private_ids: frozenset[int] = field(default_factory=frozenset)

    def allows(self, business_id: int | None) -> bool:
        """System-level rows (business_id None) are visible; business rows only if in scope."""
        return business_id is None or business_id in self.business_ids

    @property
    def ids(self) -> list[int]:
        return sorted(self.business_ids)


def build_scope(db: Session, vault_unlocked: bool) -> Scope:
    rows = db.execute(select(Business.id, Business.is_private)).all()
    private = frozenset(r.id for r in rows if r.is_private)
    visible = frozenset(r.id for r in rows if vault_unlocked or not r.is_private)
    return Scope(vault_unlocked=vault_unlocked, business_ids=visible, private_ids=private)


def system_scope(db: Session, include_private: bool) -> Scope:
    """Scope used by background jobs when producing owner-facing summaries."""
    return build_scope(db, vault_unlocked=include_private)
