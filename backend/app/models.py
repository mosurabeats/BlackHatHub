"""ORM models for Executive Hub.

Design notes
------------
* Every business-scoped table carries ``business_id`` so private-vault
  filtering can be enforced centrally (see ``app.privacy``).
* Actual financial entries (``financial_entries``) are physically separate
  from speculative opportunity values (``opportunities.estimated_value``), so
  they can never be summed together accidentally.
* Every opportunity keeps its evidence and full stage history.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

# ---------------------------------------------------------------------------
# Enumerations (stored as strings for portability)
# ---------------------------------------------------------------------------

PIPELINE_STAGES = [
    "discovered",
    "researching",
    "verified",
    "qualified",
    "awaiting_approval",
    "outreach_approved",
    "contacted",
    "negotiating",
    "active",
    "won",
    "lost",
]
STAGE_LABELS = {
    "discovered": "Discovered",
    "researching": "Researching",
    "verified": "Verified",
    "qualified": "Qualified",
    "awaiting_approval": "Awaiting Approval",
    "outreach_approved": "Outreach Approved",
    "contacted": "Contacted",
    "negotiating": "Negotiating",
    "active": "Active",
    "won": "Won",
    "lost": "Lost / Rejected",
}
# Stages that the research agents may set automatically.
INTERNAL_STAGES = {"discovered", "researching", "verified", "qualified", "lost"}
# Stages that require a decided approval / owner action.
EXTERNAL_STAGES = {"outreach_approved", "contacted", "negotiating", "active", "won"}

JOB_STATUSES = ["queued", "running", "retry_wait", "succeeded", "failed", "cancelled"]

APPROVAL_ACTION_TYPES = [
    "send_external_message",
    "contact_prospect",
    "publish_content",
    "submit_legal_document",
    "financial_commitment",
    "purchase_dataset",
    "enter_agreement",
    "initiate_payment",
    "create_external_account",
    "file_claim",
]


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# Accounts, sessions, vault
# ---------------------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    vault_unlocked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    vault_last_activity_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship()


class VaultConfig(Base):
    __tablename__ = "vault_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    pin_hash: Mapped[str] = mapped_column(String(255))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    pin_changed_at: Mapped[datetime] = mapped_column(default=utcnow)
    is_initial_pin: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))  # user:<name> | agent:<role> | system
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    business_id: Mapped[Optional[int]] = mapped_column(ForeignKey("businesses.id"), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# Businesses and CRM
# ---------------------------------------------------------------------------


class Business(TimestampMixin, Base):
    __tablename__ = "businesses"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)  # B01..B07
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    qualify_threshold: Mapped[float] = mapped_column(Float, default=60.0)
    reject_threshold: Mapped[float] = mapped_column(Float, default=20.0)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    opportunity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    organization: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual | public_record
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    opportunity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | done | cancelled
    priority: Mapped[str] = mapped_column(String(8), default="normal")
    due_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="owner")


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    business_id: Mapped[Optional[int]] = mapped_column(ForeignKey("businesses.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# Research sources, runs, opportunities, evidence
# ---------------------------------------------------------------------------


class Source(TimestampMixin, Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(96), unique=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    adapter: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    official: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # active | proposed | needs_credentials | failing | disabled
    status: Mapped[str] = mapped_column(String(32), default="active")
    discovered_by: Mapped[str] = mapped_column(String(64), default="seed")
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30)
    access_notes: Mapped[str] = mapped_column(Text, default="")
    cursor: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class ResearchRun(Base):
    __tablename__ = "research_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | succeeded | failed | partial
    current_stage: Mapped[str] = mapped_column(String(32), default="retrieve")
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    limitations: Mapped[list[Any]] = mapped_column(JSON, default=list)


class ResearchEvent(Base):
    """Audit trail of each pipeline stage within a research run."""

    __tablename__ = "research_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))  # ok | warning | error | skipped
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("business_id", "fingerprint", name="uq_opportunity_fingerprint"),
        Index("ix_opportunity_stage", "business_id", "stage"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    external_key: Mapped[str] = mapped_column(String(255), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    entity_normalized: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, index=True)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), default="discovered")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    # Published / source-reported value (e.g. unclaimed property amount, award value).
    reported_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Speculative economics -- ALWAYS estimates, never actual revenue.
    estimated_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_value_basis: Mapped[str] = mapped_column(Text, default="")
    estimated_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    regulatory_notes: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    original_source: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    deadline: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="opportunity", cascade="all, delete-orphan")
    history: Mapped[list["OpportunityHistory"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", order_by="OpportunityHistory.at"
    )


class OpportunityHistory(Base):
    __tablename__ = "opportunity_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    event: Mapped[str] = mapped_column(String(32))  # stage_change | updated | rescored | verified | note
    from_stage: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_stage: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    actor: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    opportunity: Mapped[Opportunity] = relationship(back_populates="history")


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True)
    # source_record | verification | entity_check | ai_analysis | compliance | owner_note
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(default=utcnow)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_verification: Mapped[bool] = mapped_column(Boolean, default=False)

    opportunity: Mapped[Opportunity] = relationship(back_populates="evidence")


# ---------------------------------------------------------------------------
# Jurisdictions (national asset recovery) and compliance
# ---------------------------------------------------------------------------


class Jurisdiction(TimestampMixin, Base):
    __tablename__ = "jurisdictions"
    code: Mapped[str] = mapped_column(String(4), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    agency_name: Mapped[str] = mapped_column(String(255), default="")
    agency_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    search_portal_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_availability: Mapped[str] = mapped_column(Text, default="unknown")
    bulk_data_available: Mapped[str] = mapped_column(String(16), default="unknown")  # yes | no | unknown | restricted
    finder_license_required: Mapped[str] = mapped_column(String(16), default="unknown")  # yes | no | unknown
    finder_registration: Mapped[str] = mapped_column(Text, default="")
    fee_restrictions: Mapped[str] = mapped_column(Text, default="")
    max_fee_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    waiting_period: Mapped[str] = mapped_column(Text, default="")
    claimant_authorization_rules: Mapped[str] = mapped_column(Text, default="")
    contract_requirements: Mapped[str] = mapped_column(Text, default="")
    documentation_requirements: Mapped[str] = mapped_column(Text, default="")
    statutory_references: Mapped[str] = mapped_column(Text, default="")
    source_citations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # unverified_seed | in_review | verified | needs_update
    compliance_review_status: Mapped[str] = mapped_column(String(32), default="unverified_seed")
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    verified_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    portal_status: Mapped[str] = mapped_column(String(32), default="unchecked")  # reachable | unreachable | blocked | unchecked
    portal_http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    portal_last_checked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    portal_content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    portal_changed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    operating_status: Mapped[str] = mapped_column(String(32), default="not_cleared")  # not_cleared | cleared | prohibited
    notes: Mapped[str] = mapped_column(Text, default="")


class ComplianceAlert(Base):
    __tablename__ = "compliance_alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    opportunity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning")  # info | warning | critical
    code: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | acknowledged | resolved
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    opportunity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(48))
    proposed_action: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    action_hash: Mapped[str] = mapped_column(String(64))
    justification: Mapped[str] = mapped_column(Text, default="")
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    expected_benefit: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    compliance_blockers: Mapped[list[Any]] = mapped_column(JSON, default=list)
    requested_by: Mapped[str] = mapped_column(String(64))
    # pending | approved | rejected | executed | cancelled | expired
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    execution_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Finance and AI cost accounting
# ---------------------------------------------------------------------------


class FinancialEntry(TimestampMixin, Base):
    """ACTUAL revenue or expense. Never populated from estimates."""

    __tablename__ = "financial_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # revenue | expense
    category: Mapped[str] = mapped_column(String(64), default="general")
    amount: Mapped[float] = mapped_column(Float)
    occurred_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, default="")
    opportunity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    entered_by: Mapped[str] = mapped_column(String(64), default="owner")


class Forecast(TimestampMixin, Base):
    """Owner-entered forecasts, kept separate from actuals and pipeline."""

    __tablename__ = "forecasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    expenses: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")


class AIUsage(Base):
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    agent: Mapped[str] = mapped_column(String(48))
    purpose: Mapped[str] = mapped_column(String(128), default="")
    business_id: Mapped[Optional[int]] = mapped_column(ForeignKey("businesses.id"), nullable=True, index=True)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | error | blocked_budget | refused
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AICache(Base):
    __tablename__ = "ai_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    model: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)


# ---------------------------------------------------------------------------
# Jobs and schedules
# ---------------------------------------------------------------------------


class Schedule(TimestampMixin, Base):
    __tablename__ = "schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(96), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    job_type: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[Optional[int]] = mapped_column(ForeignKey("businesses.id"), nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    missed_runs: Mapped[int] = mapped_column(Integer, default=0)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_next", "status", "next_attempt_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[Optional[int]] = mapped_column(ForeignKey("businesses.id"), nullable=True, index=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    schedule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4)
    next_attempt_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    triggered_by: Mapped[str] = mapped_column(String(64), default="schedule")
    recovered: Mapped[bool] = mapped_column(Boolean, default=False)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_beat_at: Mapped[datetime] = mapped_column(default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="running")
    jobs_processed: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# Briefings
# ---------------------------------------------------------------------------


class Briefing(Base):
    __tablename__ = "briefings"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    period_start: Mapped[datetime] = mapped_column()
    period_end: Mapped[datetime] = mapped_column()
    includes_private: Mapped[bool] = mapped_column(Boolean, default=False)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    markdown: Mapped[str] = mapped_column(Text, default="")
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(32), default="deterministic")
