"""Compliance Analyst: flags licensing, legal uncertainty and jurisdictional restrictions.

Deterministic rules only -- the system never decides that an activity is
legal. It blocks consequential actions until a human has verified the rules.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Business, ComplianceAlert, Jurisdiction, Notification, Opportunity


def raise_alert(db: Session, *, business_id: int, code: str, title: str, detail: str, severity: str = "warning",
                jurisdiction_code: str | None = None, opportunity_id: int | None = None, dedupe_key: str) -> ComplianceAlert | None:
    existing = db.execute(select(ComplianceAlert).where(ComplianceAlert.dedupe_key == dedupe_key)).scalars().first()
    if existing:
        if existing.status == "resolved":
            existing.status = "open"
        return None
    alert = ComplianceAlert(business_id=business_id, code=code, title=title, detail=detail, severity=severity,
                            jurisdiction_code=jurisdiction_code, opportunity_id=opportunity_id, dedupe_key=dedupe_key)
    db.add(alert)
    db.add(Notification(business_id=business_id, kind="compliance", severity=severity, title=title, body=detail[:400],
                        link="/compliance"))
    db.flush()
    return alert


def blockers_for(db: Session, opp: Opportunity) -> list[str]:
    """Reasons an external action on this opportunity cannot be approved yet."""
    out: list[str] = []
    if opp.category == "unclaimed_property":
        jur = db.get(Jurisdiction, opp.jurisdiction_code) if opp.jurisdiction_code else None
        if jur is None:
            out.append("Jurisdiction unknown for this property")
        else:
            if jur.compliance_review_status != "verified":
                out.append(f"{jur.name} finder/fee/contract rules have not been verified by the owner")
            if jur.operating_status != "cleared":
                out.append(f"{jur.name} not cleared for operation (operating status: {jur.operating_status})")
        if opp.data.get("entity_check", {}).get("status") != "match":
            out.append("Claimant entity identity not confirmed against an official registry")
    return out


def review_opportunity(db: Session, opp: Opportunity, business: Business) -> list[str]:
    notes: list[str] = []
    now = datetime.now(timezone.utc)
    if opp.category == "unclaimed_property":
        jur = db.get(Jurisdiction, opp.jurisdiction_code) if opp.jurisdiction_code else None
        if jur and jur.compliance_review_status != "verified":
            notes.append(
                f"{jur.name}: finder licensing, fee caps, waiting periods and contract requirements are UNVERIFIED. "
                "Do not contact the owner, sign agreements or file claims until verified."
            )
            raise_alert(db, business_id=business.id, code="jurisdiction_unverified", jurisdiction_code=jur.code,
                        title=f"{jur.name} unclaimed-property rules need verification",
                        detail=f"Opportunities exist in {jur.name} but its finder/fee/contract rules are not verified. "
                               f"Review the official agency ({jur.agency_url}) and statutes, then mark the jurisdiction verified.",
                        dedupe_key=f"jur_unverified:{business.id}:{jur.code}")
        if opp.data.get("holder_type") == "municipal":
            notes.append("Property is held by a local government, not the state program; confirm which statute governs claims "
                         "and whether finder agreements are recognised by this holder.")
    if opp.category == "solicitation" and opp.deadline and opp.deadline - now < timedelta(days=7) and opp.deadline > now:
        raise_alert(db, business_id=business.id, code="deadline_near", severity="info", opportunity_id=opp.id,
                    title=f"Response deadline within 7 days: {opp.title[:80]}",
                    detail=f"Deadline {opp.deadline.isoformat()}", dedupe_key=f"deadline:{opp.id}")
    if opp.category == "building_permit":
        notes.append("Permit contact details are public records; outreach must comply with CAN-SPAM/TCPA and state telemarketing rules.")
    if business.is_private:
        notes.append("Private venture: all content must involve consenting adults (18+) or fictional adult characters only; "
                     "maintain age/consent records where real performers are involved (e.g. 18 U.S.C. 2257) and follow platform terms.")
    return notes


def jurisdiction_alerts(db: Session, business_id: int) -> int:
    """Raise alerts for portals that changed or became unreachable."""
    n = 0
    for jur in db.execute(select(Jurisdiction)).scalars():
        if jur.portal_status == "unreachable":
            if raise_alert(db, business_id=business_id, code="portal_unreachable", jurisdiction_code=jur.code, severity="info",
                           title=f"{jur.name} portal unreachable", detail=f"{jur.search_portal_url} could not be reached on last check.",
                           dedupe_key=f"portal_unreachable:{jur.code}:{(jur.portal_last_checked_at or datetime.now(timezone.utc)).date()}"):
                n += 1
        if jur.portal_changed_at and jur.last_verified_at and jur.portal_changed_at > jur.last_verified_at:
            if raise_alert(db, business_id=business_id, code="portal_changed", jurisdiction_code=jur.code,
                           title=f"{jur.name} agency page changed since last verification",
                           detail="The official page content changed after rules were verified; re-review for rule changes.",
                           dedupe_key=f"portal_changed:{jur.code}:{jur.portal_changed_at.isoformat()}"):
                n += 1
    return n
