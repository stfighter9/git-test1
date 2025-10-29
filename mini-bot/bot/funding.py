"""Funding rate helpers."""
from __future__ import annotations

from typing import Iterable, Literal, Optional, Tuple

# (funding_rate_per_period, mark_price)
FundingEvent = Tuple[float, float]


def estimate_annualized_funding(
    next_rate: float,
    hours_window: int = 8,
    *,
    method: Literal["simple", "compounded"] = "simple",
    clamp: Optional[float] = None,
) -> float:
    """Convert a per-period funding rate into an annualised figure.

    Args:
        next_rate: Funding rate for a single accrual period (e.g. 8 hours).
        hours_window: Length of the accrual window, in hours.
        method: ``"simple"`` multiplies the rate by periods-per-year while
            ``"compounded"`` applies geometric compounding.
        clamp: Optional absolute cap for the annualised result to guard
            against extreme outliers.
    """

    if hours_window <= 0:
        return 0.0

    periodic = float(next_rate)
    periods_per_year = 24 * 365 / float(hours_window)

    if method == "compounded":
        annualised = (1.0 + periodic) ** periods_per_year - 1.0
    else:
        annualised = periodic * periods_per_year

    if clamp is not None:
        if annualised > clamp:
            annualised = clamp
        elif annualised < -clamp:
            annualised = -clamp

    return annualised


def accrue_funding_linear(
    position,
    events: Iterable[FundingEvent],
    *,
    long_pays_when_positive: bool = True,
) -> float:
    """Accrue funding PnL for a linear (quote margined) perpetual contract.

    Returns the funding result in quote currency (e.g. USDT) with the
    convention that positive values are gains to the position holder.
    """

    qty = float(getattr(position, "qty", 0.0))
    if qty == 0:
        return 0.0

    side = getattr(position, "side", None)
    if side is None:
        side = "buy" if qty > 0 else "sell"

    total = 0.0
    for rate, mark in events:
        notional = abs(qty) * float(mark)
        if long_pays_when_positive:
            sign = -1.0 if side == "buy" else 1.0
        else:
            sign = 1.0 if side == "buy" else -1.0
        total += sign * notional * float(rate)

    return total


def accrue_funding_inverse(
    position,
    events: Iterable[FundingEvent],
    *,
    contract_size: float,
    long_pays_when_positive: bool = True,
) -> float:
    """Accrue funding for an inverse (coin margined) contract.

    ``contract_size`` corresponds to the notional value of a single contract
    in quote currency terms. The result is returned in quote currency.
    """

    qty = float(getattr(position, "qty", 0.0))
    if qty == 0:
        return 0.0

    side = getattr(position, "side", None)
    if side is None:
        side = "buy" if qty > 0 else "sell"

    total = 0.0
    for rate, _ in events:
        if long_pays_when_positive:
            sign = -1.0 if side == "buy" else 1.0
        else:
            sign = 1.0 if side == "buy" else -1.0
        total += sign * contract_size * abs(qty) * float(rate)

    return total


__all__ = [
    "FundingEvent",
    "estimate_annualized_funding",
    "accrue_funding_linear",
    "accrue_funding_inverse",
]
