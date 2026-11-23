"""Per-model list prices (USD per 1M tokens) used for cost accounting.

Anthropic prices: Anthropic first-party list prices as of 2026-11. OpenAI
entries are placeholders that the owner must confirm in Settings
(``ai_pricing_overrides``); costs computed from them are flagged as
estimates. Update this table if provider pricing changes.
"""
from __future__ import annotations

PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-2": (8.00, 40.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
}
# Unknown models are costed conservatively so budgets err on the safe side.
CONSERVATIVE_DEFAULT = (10.00, 50.00)
VERIFIED_MODELS = set(PRICES)


def price_for(model: str, overrides: dict | None = None) -> tuple[float, float, bool]:
    """Return (input_per_mtok, output_per_mtok, is_verified_price)."""
    if overrides and model in overrides:
        p = overrides[model]
        return float(p[0]), float(p[1]), False
    if model in PRICES:
        return (*PRICES[model], True)
    return (*CONSERVATIVE_DEFAULT, False)


def cost(model: str, input_tokens: int, output_tokens: int, overrides: dict | None = None) -> tuple[float, bool]:
    pin, pout, verified = price_for(model, overrides)
    return round(input_tokens / 1e6 * pin + output_tokens / 1e6 * pout, 6), verified


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 3.5))
