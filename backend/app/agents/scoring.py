"""Opportunity Analyst: deterministic, explainable scoring per business.

All monetary outputs are ESTIMATES with an explicit basis string. A published
property value is never treated as recoverable revenue: estimated revenue is
(value x permitted/assumed fee) x success probability - cost to pursue.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..models import Jurisdiction, Opportunity


@dataclass
class ScoreResult:
    score: float
    breakdown: dict[str, Any]
    confidence: float
    estimated_value: float | None
    estimated_value_basis: str
    estimated_cost: float | None
    expected_value: float | None
    recommended_action: str
    risks: list[str] = field(default_factory=list)
    reject_reason: str | None = None


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _log_scale(v: float | None, lo: float, hi: float) -> float:
    if not v or v <= 0:
        return 0.0
    return _clamp((math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)))


def score_asset_recovery(opp: Opportunity, jur: Jurisdiction | None, settings: dict[str, Any]) -> ScoreResult:
    value = opp.reported_value
    risks: list[str] = []
    verified_rules = jur is not None and jur.compliance_review_status == "verified"
    if jur is not None and jur.operating_status == "prohibited":
        return ScoreResult(0, {"jurisdiction": "prohibited"}, 0.9, None, "Jurisdiction marked prohibited for finder activity.",
                           None, None, "Do not pursue.", ["Jurisdiction prohibits this activity"],
                           reject_reason=f"{jur.code}: finder activity marked prohibited")
    if verified_rules and jur.max_fee_percent is not None:
        fee_pct, fee_basis = jur.max_fee_percent, f"verified {jur.code} fee cap {jur.max_fee_percent}%"
    else:
        fee_pct = float(settings["asset_recovery_assumed_fee_percent"])
        fee_basis = f"ASSUMED fee {fee_pct}% (jurisdiction fee rules not verified)"
        risks.append("Finder fee limits not verified for this jurisdiction")
    cost_to_pursue = float(settings["asset_recovery_cost_per_claim_usd"])
    entity_verified = opp.data.get("entity_check", {}).get("status") == "match"
    id_conf = 0.85 if entity_verified else 0.55
    if opp.data.get("entity_check", {}).get("status") == "no_match":
        id_conf = 0.45
        risks.append("Entity not found in state registry check (may be dissolved, renamed or out-of-state)")
    reg_factor = 0.9 if verified_rules else 0.5
    if opp.data.get("holder_type") == "municipal":
        risks.append("Held by a municipality: claim process and finder rules may differ from the state program")
    doc_burden = 0.6 if opp.data.get("holder_type") == "municipal" else 0.5
    success_prob = round(0.45 * id_conf * reg_factor + 0.1, 3)
    if value is None:
        breakdown = {"value": 0, "identification": id_conf, "regulatory": reg_factor, "evidence": 0.9}
        sc = round(15 + 20 * id_conf, 1)
        return ScoreResult(sc, breakdown, round(0.5 * id_conf, 2), None,
                           "Property value not published by holder; economics cannot be estimated.", cost_to_pursue, None,
                           "Low priority: confirm property value through the holder's official claim inquiry before investing effort.",
                           risks + ["Value unknown"])
    gross_fee = value * fee_pct / 100.0
    expected = round(gross_fee * success_prob - cost_to_pursue, 2)
    competition = _clamp(_log_scale(value, 1_000, 1_000_000))  # larger claims attract more finders
    if competition > 0.5:
        risks.append("Large published claims are typically contacted by competing finders")
    breakdown = {
        "value": round(_log_scale(value, 100, 250_000), 3),
        "fee_permitted": round(_clamp(fee_pct / 20.0), 3),
        "identification": id_conf,
        "regulatory": reg_factor,
        "documentation": doc_burden,
        "competition_penalty": round(competition * 0.5, 3),
        "evidence": 0.9 if opp.verification_status.startswith("source_record") or entity_verified else 0.6,
    }
    raw = (
        30 * breakdown["value"] + 10 * breakdown["fee_permitted"] + 20 * id_conf + 15 * reg_factor
        + 10 * breakdown["evidence"] + 10 * (1 - doc_burden) + 5 * (1 - breakdown["competition_penalty"])
    )
    if expected <= 0:
        raw = min(raw, 35)
    reject = None
    min_value = float(settings["asset_recovery_min_value_usd"])
    if value < min_value:
        reject = f"Published value ${value:,.2f} is below the ${min_value:,.0f} economic threshold"
    action = (
        "Verify claimant entity and jurisdiction finder rules; then request owner approval for compliant outreach."
        if not verified_rules else "Prepare compliant outreach approval request with the jurisdiction's required disclosures."
    )
    return ScoreResult(
        round(raw, 1), breakdown, round(_clamp(0.4 + 0.5 * id_conf * reg_factor), 2), round(gross_fee * success_prob, 2),
        f"${value:,.2f} published value x {fee_basis} x {success_prob:.0%} est. success probability. ESTIMATE ONLY.",
        cost_to_pursue, expected, action, risks, reject,
    )


def score_permit(opp: Opportunity, settings: dict[str, Any]) -> ScoreResult:
    value = opp.reported_value
    issued = opp.retrieved_at or datetime.now(timezone.utc)
    rate = float(opp.data.get("assumed_service_rate", 0.005))
    contacts = len(opp.data.get("contacts", [])) if isinstance(opp.data.get("contacts"), list) else 0
    b = {
        "project_size": round(_log_scale(value, 50_000, 50_000_000), 3),
        "contact_available": 1.0 if opp.entity_name else 0.3,
        "evidence": 0.9,
    }
    raw = 55 * b["project_size"] + 25 * b["contact_available"] + 20 * b["evidence"]
    est = round(value * rate, 2) if value else None
    return ScoreResult(
        round(raw, 1), b, 0.7, est,
        f"ASSUMPTION: {rate:.1%} service/referral value of reported project cost ${value:,.0f}." if value else "Project cost not reported.",
        250.0, round(est * 0.15 - 250, 2) if est else None,
        "Identify the general contractor/developer from the permit record and prepare an approval request for introductory outreach.",
        ["Reported permit cost is the applicant's estimate", "Permit contacts may be agents rather than decision makers"]
        + ([] if contacts else ["No named contact in permit record"]),
        None if (value or 0) > 0 else "No reported project cost",
    )


def score_procurement(opp: Opportunity, settings: dict[str, Any]) -> ScoreResult:
    value = opp.reported_value
    now = datetime.now(timezone.utc)
    days = (opp.deadline - now).days if opp.deadline else None
    timing = 0.0
    if days is not None:
        timing = 1.0 if 90 <= days <= 365 else 0.6 if 30 <= days < 90 or 365 < days <= 540 else 0.2
    b = {"contract_size": round(_log_scale(value, 25_000, 100_000_000), 3), "timing": timing, "evidence": 0.95}
    raw = 50 * b["contract_size"] + 35 * timing + 15 * b["evidence"]
    risks = ["Expiring award may be extended or bundled rather than re-competed", "Incumbent advantage"]
    if opp.category == "solicitation":
        risks = ["Verify eligibility, set-aside and registration (SAM UEI) requirements before bidding"]
    return ScoreResult(
        round(raw, 1), b, 0.75, None,
        f"Reported contract value ${value:,.0f} is the government's obligation, NOT revenue to us." if value else "Value not reported.",
        500.0, None,
        "Monitor SAM.gov for the follow-on solicitation; identify teaming partners; review incumbent performance.",
        risks, None,
    )


def score_closure(opp: Opportunity, settings: dict[str, Any]) -> ScoreResult:
    workers = opp.data.get("affected_workers") or 0
    b = {"facility_size": round(_log_scale(float(workers or 0), 10, 2000), 3),
         "recency": 1.0 if opp.deadline and opp.deadline >= datetime.now(timezone.utc) else 0.4, "evidence": 0.9}
    raw = 50 * b["facility_size"] + 30 * b["recency"] + 20 * b["evidence"]
    return ScoreResult(
        round(raw, 1), b, 0.5, None,
        "No asset inventory or pricing available; brokerage economics cannot be estimated from a WARN notice.",
        150.0, None,
        "Research whether the site has disposable equipment (facility type, public auction listings) before any outreach.",
        ["WARN notices signal layoffs/closures, not asset sales", "Assets may already be committed to an auctioneer or lender"],
        None,
    )


def score_signal(opp: Opportunity, settings: dict[str, Any]) -> ScoreResult:
    ai = opp.data.get("ai_analysis") or {}
    rel = ai.get("relevance")
    if rel is None:
        return ScoreResult(20.0, {"relevance": None}, 0.3, None, "Unstructured signal; not analysed.", None, None,
                           "Review manually or enable AI analysis.", ["Unanalysed news/feed item"])
    rel = _clamp(float(rel) / 100.0)
    return ScoreResult(round(70 * rel + 10, 1), {"relevance": rel}, round(0.3 + 0.4 * rel, 2), None,
                       "Market-intelligence item; no direct revenue estimate.", None, None,
                       ai.get("suggested_next_step") or "Review for strategic relevance.",
                       ["AI-assessed relevance; verify against the source"])


def score(opp: Opportunity, business_slug: str, jur: Jurisdiction | None, settings: dict[str, Any]) -> ScoreResult:
    if opp.category == "unclaimed_property":
        return score_asset_recovery(opp, jur, settings)
    if opp.category == "building_permit":
        return score_permit(opp, settings)
    if opp.category in ("contract_recompete", "solicitation"):
        return score_procurement(opp, settings)
    if opp.category == "closure_signal":
        return score_closure(opp, settings)
    return score_signal(opp, settings)
