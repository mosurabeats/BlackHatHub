"""Deterministic normalization helpers (entity names, money, dates)."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

_CORP_SUFFIXES = [
    "LLC", "L L C", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED",
    "LP", "LLP", "PLLC", "PC", "PA", "LLLP", "TRUST", "BANK", "PARTNERS", "PARTNERSHIP", "HOLDINGS",
    "ASSOCIATES", "ASSOCIATION", "GROUP", "ENTERPRISES", "INDUSTRIES", "SERVICES", "SYSTEMS",
    "FOUNDATION", "AUTHORITY", "HOSPITAL", "UNIVERSITY", "COLLEGE", "CHURCH", "CLINIC", "APARTMENTS",
    "PROPERTIES", "INVESTMENTS", "MANAGEMENT", "DEVELOPMENT", "CONSTRUCTION", "CONTRACTORS", "REALTY",
    "INSURANCE", "TECHNOLOGIES", "SOLUTIONS", "PLLC", "NA", "N A", "FCU", "CU",
]
_CORP_RE = re.compile(r"\b(" + "|".join(re.escape(s) for s in _CORP_SUFFIXES) + r")\b\.?$")
_CORP_ANYWHERE = re.compile(r"\b(LLC|INC|CORP|CORPORATION|COMPANY|LTD|LLP|L\.L\.C|HOLDINGS|PROPERTIES|PARTNERS|ENTERPRISES|ASSOCIATES|MANAGEMENT|BANK|TRUST CO|APARTMENTS|SERVICES|GROUP)\b")
_STRIP_SUFFIX = re.compile(r"\b(LLC|L L C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|LP|LLP|PLLC|PC)\b\.?", re.I)


def clean_text(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(value))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def normalize_entity(name: str | None) -> str:
    if not name:
        return ""
    s = name.upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = _STRIP_SUFFIX.sub(" ", s)
    s = re.sub(r"\bTHE\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def looks_corporate(name: str | None) -> bool:
    """Heuristic: does the owner name look like a business entity (not a person)?"""
    if not name:
        return False
    up = re.sub(r"[.,]", " ", name.upper())
    up = re.sub(r"\s+", " ", up).strip()
    if _CORP_RE.search(up) or _CORP_ANYWHERE.search(up):
        return True
    # Names starting with a street number ("1200 WINDSOR ...") are typically property entities.
    return bool(re.match(r"^\d{2,6} [A-Z]", up)) and len(up.split()) >= 3


def parse_money(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(re.sub(r"[^0-9.\-]", "", str(value))), 2)
    except ValueError:
        return None


def parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            d = datetime.strptime(s.replace("Z", "+0000") if fmt.endswith("%z") else s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def fingerprint(*parts: Any) -> str:
    raw = "|".join(normalize_entity(str(p)) if isinstance(p, str) else str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def content_hash(data: Any) -> str:
    import json

    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
