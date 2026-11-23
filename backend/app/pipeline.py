"""Pipeline Manager: stage transitions and approval-based execution rules.

Rules enforced here (server-side, independent of the UI):

* Agents / system may move opportunities only through INTERNAL research
  stages (discovered -> researching -> verified -> qualified, or lost), and to
  ``awaiting_approval`` only by filing an approval request.
* ``outreach_approved`` requires an APPROVED, unconsumed approval for that
  opportunity whose action hash matches what was approved.
* ``contacted``/``negotiating``/``active``/``won`` are owner-only and require
  that outreach was previously approved.
* Every change writes an OpportunityHistory row.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import audit
from .models import (
    APPROVAL_ACTION_TYPES,
    EXTERNAL_STAGES,
    INTERNAL_STAGES,
    PIPELINE_STAGES,
    Approval,
    Notification,
    Opportunity,
    OpportunityHistory,
)

APPROVAL_TTL_DAYS = 14


class TransitionError(Exception):
    pass


class ApprovalError(Exception):
    pass


def is_owner(actor: str) -> bool:
    return actor.startswith("user:")


def record_history(db: Session, opp: Opportunity, event: str, actor: str, reason: str = "", *,
                   from_stage: str | None = None, to_stage: str | None = None, changes: dict | None = None) -> None:
    db.add(OpportunityHistory(opportunity_id=opp.id, event=event, actor=actor, reason=reason,
                              from_stage=from_stage, to_stage=to_stage, changes=changes or {}))


def _has_approved_outreach(db: Session, opp: Opportunity) -> bool:
    return db.execute(
        select(Approval.id).where(Approval.opportunity_id == opp.id, Approval.status.in_(["approved", "executed"]))
    ).first() is not None


def transition(db: Session, opp: Opportunity, to_stage: str, actor: str, reason: str = "") -> None:
    if to_stage not in PIPELINE_STAGES:
        raise TransitionError(f"Unknown stage '{to_stage}'")
    if to_stage == opp.stage:
        return
    if not is_owner(actor):
        if to_stage not in INTERNAL_STAGES:
            raise TransitionError(f"Automated actor '{actor}' may not move an opportunity to '{to_stage}'")
        if opp.stage not in INTERNAL_STAGES and to_stage != "lost":
            raise TransitionError("Automated actors may not pull an opportunity back from an owner-controlled stage")
        if opp.stage not in INTERNAL_STAGES and to_stage == "lost":
            raise TransitionError("Only the owner may close an opportunity that is in an owner-controlled stage")
    else:
        if to_stage == "awaiting_approval":
            raise TransitionError("Use an approval request to move an opportunity to Awaiting Approval")
        if to_stage == "outreach_approved":
            raise TransitionError("Outreach Approved is set only by approving a specific approval request")
        if to_stage in EXTERNAL_STAGES and not _has_approved_outreach(db, opp):
            raise TransitionError(f"'{to_stage}' requires a previously approved outreach action for this opportunity")
    frm = opp.stage
    opp.stage = to_stage
    if to_stage == "lost" and reason:
        opp.rejected_reason = reason
    record_history(db, opp, "stage_change", actor, reason, from_stage=frm, to_stage=to_stage)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


def action_hash(action_type: str, proposed_action: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps([action_type, proposed_action, payload], sort_keys=True, default=str).encode()).hexdigest()


def request_approval(
    db: Session,
    *,
    business_id: int,
    action_type: str,
    proposed_action: str,
    justification: str,
    evidence_summary: str,
    expected_benefit: str,
    risks: str,
    estimated_cost_usd: float,
    requested_by: str,
    opportunity: Opportunity | None = None,
    payload: dict[str, Any] | None = None,
) -> Approval:
    if action_type not in APPROVAL_ACTION_TYPES:
        raise ApprovalError(f"Unknown action type '{action_type}'")
    for name, val in [("proposed_action", proposed_action), ("justification", justification),
                      ("expected_benefit", expected_benefit), ("risks", risks)]:
        if not val or not val.strip():
            raise ApprovalError(f"Approval request must include {name}")
    payload = payload or {}
    if opportunity is not None:
        existing = db.execute(select(Approval).where(Approval.opportunity_id == opportunity.id,
                                                     Approval.status == "pending")).scalars().first()
        if existing:
            raise ApprovalError("An approval request is already pending for this opportunity")
    ap = Approval(
        business_id=business_id,
        opportunity_id=opportunity.id if opportunity else None,
        action_type=action_type,
        proposed_action=proposed_action.strip(),
        payload=payload,
        action_hash=action_hash(action_type, proposed_action.strip(), payload),
        justification=justification,
        evidence_summary=evidence_summary,
        expected_benefit=expected_benefit,
        risks=risks,
        estimated_cost_usd=float(estimated_cost_usd or 0),
        requested_by=requested_by,
        expires_at=datetime.now(timezone.utc) + timedelta(days=APPROVAL_TTL_DAYS),
    )
    db.add(ap)
    db.flush()
    if opportunity is not None and opportunity.stage in INTERNAL_STAGES and opportunity.stage != "lost":
        frm = opportunity.stage
        opportunity.stage = "awaiting_approval"
        record_history(db, opportunity, "stage_change", requested_by, f"Approval #{ap.id} requested: {action_type}",
                       from_stage=frm, to_stage="awaiting_approval")
    db.add(Notification(business_id=business_id, kind="approval", severity="action",
                        title=f"Approval needed: {action_type.replace('_', ' ')}",
                        body=proposed_action[:300], link=f"/approvals/{ap.id}"))
    audit(db, requested_by, "approval.requested", target_type="approval", target_id=ap.id, business_id=business_id,
          detail={"action_type": action_type})
    return ap


def _expire_if_needed(ap: Approval) -> None:
    if ap.status == "pending" and ap.expires_at and ap.expires_at < datetime.now(timezone.utc):
        ap.status = "expired"


def decide_approval(db: Session, ap: Approval, *, approve: bool, actor: str, note: str = "",
                    confirm_hash: str | None = None) -> Approval:
    if not is_owner(actor):
        raise ApprovalError("Only the owner can decide approvals")
    _expire_if_needed(ap)
    if ap.status != "pending":
        raise ApprovalError(f"Approval is {ap.status}; it can no longer be decided")
    if approve:
        if ap.compliance_blockers:
            raise ApprovalError("Approval has unresolved compliance blockers: " + "; ".join(map(str, ap.compliance_blockers)))
        if confirm_hash is None or confirm_hash != ap.action_hash:
            raise ApprovalError("Confirmation hash does not match the exact proposed action")
    ap.status = "approved" if approve else "rejected"
    ap.decided_by = actor
    ap.decided_at = datetime.now(timezone.utc)
    ap.decision_note = note
    opp = db.get(Opportunity, ap.opportunity_id) if ap.opportunity_id else None
    if opp is not None and opp.stage == "awaiting_approval":
        frm = opp.stage
        opp.stage = "outreach_approved" if approve else "qualified"
        record_history(db, opp, "stage_change", actor,
                       f"Approval #{ap.id} {'approved' if approve else 'rejected'}" + (f": {note}" if note else ""),
                       from_stage=frm, to_stage=opp.stage)
    audit(db, actor, "approval.approved" if approve else "approval.rejected", target_type="approval",
          target_id=ap.id, business_id=ap.business_id, detail={"note": note})
    return ap


def mark_executed(db: Session, ap: Approval, *, actor: str, result: str) -> Approval:
    """Record that the single authorized action was carried out (consumes the approval)."""
    if not is_owner(actor):
        raise ApprovalError("Only the owner can record execution of an approved action")
    if ap.status != "approved":
        raise ApprovalError(f"Only approved actions can be executed (status: {ap.status})")
    if action_hash(ap.action_type, ap.proposed_action, ap.payload) != ap.action_hash:
        raise ApprovalError("Approved action was modified after approval; execution refused")
    ap.status = "executed"
    ap.executed_at = datetime.now(timezone.utc)
    ap.execution_result = result
    audit(db, actor, "approval.executed", target_type="approval", target_id=ap.id, business_id=ap.business_id,
          detail={"result": result[:500]})
    return ap


def assert_authorized(db: Session, approval_id: int, action_type: str, payload: dict[str, Any]) -> Approval:
    """Gate for any future external executor: the specific action must be approved."""
    ap = db.get(Approval, approval_id)
    if ap is None or ap.status != "approved":
        raise ApprovalError("No approved authorization for this action")
    if ap.action_type != action_type or action_hash(ap.action_type, ap.proposed_action, payload) != ap.action_hash:
        raise ApprovalError("Authorization does not cover this exact action")
    return ap
