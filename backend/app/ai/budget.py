"""Cost Controller: AI spend accounting and budget enforcement."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..app_settings import get_setting
from ..models import AIUsage


class BudgetExceeded(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _sum_since(db: Session, since: datetime, job_id: int | None = None) -> float:
    q = select(func.coalesce(func.sum(AIUsage.cost_usd), 0.0)).where(AIUsage.at >= since, AIUsage.status == "ok")
    if job_id is not None:
        q = select(func.coalesce(func.sum(AIUsage.cost_usd), 0.0)).where(AIUsage.job_id == job_id, AIUsage.status == "ok")
    return float(db.execute(q).scalar_one())


def period_starts(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    return day, month


def spend_summary(db: Session, business_ids: list[int] | None = None) -> dict:
    """Spend totals. When ``business_ids`` given, only rows for those businesses
    plus system rows (business_id NULL) are counted (private-vault safe)."""
    day, month = period_starts()

    def total(since):
        q = select(func.coalesce(func.sum(AIUsage.cost_usd), 0.0)).where(AIUsage.at >= since, AIUsage.status == "ok")
        if business_ids is not None:
            q = q.where((AIUsage.business_id.is_(None)) | (AIUsage.business_id.in_(business_ids)))
        return round(float(db.execute(q).scalar_one()), 4)

    return {
        "today_usd": total(day),
        "month_usd": total(month),
        "daily_budget_usd": float(get_setting(db, "ai_daily_budget_usd")),
        "monthly_budget_usd": float(get_setting(db, "ai_monthly_budget_usd")),
        "hard_limit": bool(get_setting(db, "ai_hard_limit")),
        "warning_ratio": float(get_setting(db, "ai_warning_ratio")),
    }


def check_budget(db: Session, estimated_cost: float, job_id: int | None = None) -> list[str]:
    """Raise BudgetExceeded if a hard limit would be crossed; return warnings otherwise."""
    day, month = period_starts()
    daily_limit = float(get_setting(db, "ai_daily_budget_usd"))
    monthly_limit = float(get_setting(db, "ai_monthly_budget_usd"))
    job_limit = float(get_setting(db, "ai_job_budget_usd"))
    hard = bool(get_setting(db, "ai_hard_limit"))
    ratio = float(get_setting(db, "ai_warning_ratio"))
    max_per_hour = int(get_setting(db, "ai_max_requests_per_hour"))

    spent_day = _sum_since(db, day)
    spent_month = _sum_since(db, month)
    problems, warnings = [], []
    if spent_day + estimated_cost > daily_limit:
        problems.append(f"daily AI budget ${daily_limit:.2f} (spent ${spent_day:.4f})")
    if spent_month + estimated_cost > monthly_limit:
        problems.append(f"monthly AI budget ${monthly_limit:.2f} (spent ${spent_month:.4f})")
    if job_id is not None:
        spent_job = _sum_since(db, day, job_id=job_id)
        if spent_job + estimated_cost > job_limit:
            problems.append(f"per-job AI budget ${job_limit:.2f} (spent ${spent_job:.4f})")
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    n_hour = db.execute(select(func.count(AIUsage.id)).where(AIUsage.at >= hour_ago, AIUsage.cached.is_(False))).scalar_one()
    if n_hour >= max_per_hour:
        problems.append(f"request limit {max_per_hour}/hour")
    if problems:
        if hard:
            raise BudgetExceeded("Would exceed " + "; ".join(problems))
        warnings.extend(problems)
    if spent_month > monthly_limit * ratio:
        warnings.append(f"Monthly AI spend at {spent_month / monthly_limit:.0%} of budget")
    return warnings
