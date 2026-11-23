"""Owner-adjustable runtime settings stored in the database (non-secret)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import Setting

DEFAULTS: dict[str, Any] = {
    # Cost control (USD)
    "monthly_operating_budget_usd": 100.0,
    "ai_monthly_budget_usd": 60.0,
    "ai_daily_budget_usd": 3.0,
    "ai_job_budget_usd": 0.50,
    "ai_hard_limit": True,
    "ai_warning_ratio": 0.8,
    "ai_max_requests_per_hour": 120,
    # Model routing -- roles map to (provider, model). Bulk extraction uses the
    # small model; analysis/briefings use the default analysis model.
    "ai_routes": {
        "bulk_extraction": {"provider": "anthropic", "model": "claude-haiku-5-5"},
        "analysis": {"provider": "anthropic", "model": "claude-opus-5-5"},
        "briefing": {"provider": "anthropic", "model": "claude-opus-5-5"},
    },
    "ai_briefing_summary_enabled": True,
    # {"model-id": [input_usd_per_mtok, output_usd_per_mtok]} -- e.g. OpenAI models
    "ai_pricing_overrides": {},
    # Research
    "stale_after_days": 30,
    "research_max_records_per_run": 500,
    "auto_request_approvals": True,
    "max_auto_approvals_per_cycle": 5,
    # Asset recovery economics assumptions (clearly labelled as assumptions)
    "asset_recovery_assumed_fee_percent": 10.0,
    "asset_recovery_min_value_usd": 250.0,
    "asset_recovery_cost_per_claim_usd": 75.0,
    "briefing_interval_hours": 24,
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(Setting, key)
    if row is None:
        return DEFAULTS.get(key)
    return row.value


def set_setting(db: Session, key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def all_settings(db: Session) -> dict[str, Any]:
    out = dict(DEFAULTS)
    for row in db.query(Setting).all():
        if row.key in DEFAULTS:
            out[row.key] = row.value
    return out
