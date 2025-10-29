"""Definition of Done validation."""
from __future__ import annotations

from typing import Dict


def check_dod(metrics: Dict[str, float]) -> bool:
    if not metrics:
        return False
    if metrics.get("Sharpe", 0.0) < 1.0:
        return False
    if metrics.get("MAR", 0.0) < 0.6:
        return False
    if metrics.get("MaxDD", 1.0) > 0.15:
        return False
    if metrics.get("FillRatio", 0.0) < 0.55:
        return False
    if metrics.get("BTC_Sharpe", 0.0) <= 0:
        return False
    if metrics.get("ETH_Sharpe", 0.0) <= 0:
        return False
    return True


__all__ = ["check_dod"]
