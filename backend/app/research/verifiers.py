"""Verification against authoritative sources.

* ``texas_franchise_tax``: Texas Comptroller "Active Franchise Tax Permit
  Holders" open dataset (data.texas.gov 9cir-efmm). A match is positive
  evidence that the entity exists and holds an active permit. Absence is NOT
  evidence of dissolution (name variants, out-of-state entities, exemptions).
"""
from __future__ import annotations

from typing import Any

from .normalize import normalize_entity

TX_DATASET = "https://data.texas.gov/resource/9cir-efmm.json"


def texas_entity_lookup(http, names: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-lookup entity names. Returns {normalized_name: record} for matches."""
    out: dict[str, dict[str, Any]] = {}
    clean = [n.upper().replace("'", "''") for n in names if n]
    for i in range(0, len(clean), 40):
        chunk = clean[i : i + 40]
        where = "upper(taxpayer_name) in (" + ",".join(f"'{c}'" for c in chunk) + ")"
        resp = http.get(TX_DATASET, params={"$where": where, "$limit": 200}, rate_per_minute=30)
        for row in resp.json():
            out[normalize_entity(row.get("taxpayer_name"))] = row
    return out


def texas_record_summary(row: dict[str, Any]) -> str:
    status = {"A": "active"}.get(row.get("sos_status_code", ""), row.get("sos_status_code") or "unknown")
    return (
        f"Texas Comptroller franchise-tax record: {row.get('taxpayer_name')} (taxpayer #{row.get('taxpayer_number')}), "
        f"SOS status '{status}', right to transact '{row.get('right_to_transact_business_code') or 'n/a'}', "
        f"address {row.get('taxpayer_city') or ''} {row.get('taxpayer_state') or ''}."
    )
