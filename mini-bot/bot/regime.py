"""Trading regime filters and gating helpers."""
from __future__ import annotations

import math
from typing import Optional, Tuple


def _is_finite(value: Optional[float]) -> bool:
    return value is not None and math.isfinite(value)


def allow_trade(
    adx: Optional[float],
    atr_pct: Optional[float],
    *,
    adx_min: float = 25.0,
    atr_pct_min: float = 0.20,
    atr_pct_max: float = 0.80,
    prev_allowed: Optional[bool] = None,
    adx_min_exit_delta: float = 2.0,
    atr_pct_margin: float = 0.02,
) -> Tuple[bool, str]:
    """Return the regime verdict and the associated reason."""

    if not _is_finite(adx):
        return False, "err:adx_nan"
    if not _is_finite(atr_pct):
        return False, "err:atr_nan"
    if atr_pct <= 0:
        return False, "rej:atr_nonpos"

    entering_adx_ok = adx >= adx_min
    entering_vol_ok = atr_pct_min <= atr_pct <= atr_pct_max

    if prev_allowed:
        exit_adx_floor = max(0.0, adx_min - adx_min_exit_delta)
        exit_vol_min = max(0.0, atr_pct_min - atr_pct_margin)
        exit_vol_max = atr_pct_max + atr_pct_margin

        if adx < exit_adx_floor:
            return False, "exit:adx_drop"
        if atr_pct < exit_vol_min or atr_pct > exit_vol_max:
            return False, "exit:atr_outside"
        return True, "keep"

    if not entering_adx_ok:
        return False, "rej:adx_low"
    if not entering_vol_ok:
        return False, "rej:atr_outside"
    return True, "enter"


__all__ = ["allow_trade"]
