"""Signal policy derived from model probabilities."""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

from bot.config import DEFAULT_TAU, TradingConfig

MIN_STOP_PCT = 0.001  # 0.1% tối thiểu để tránh SL quá sát


def _finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _normalise_probs(proba: Optional[Mapping[str, float]]) -> Optional[Dict[str, float]]:
    if proba is None:
        return None

    buy = float(proba.get("buy", 0.0))
    sell = float(proba.get("sell", 0.0))

    buy = max(0.0, min(1.0, buy))
    sell = max(0.0, min(1.0, sell))

    total = buy + sell
    if total == 0:
        return {"buy": 0.0, "sell": 0.0}

    return {"buy": buy / total, "sell": sell / total}


def make_signal(
    proba: Optional[Mapping[str, float]],
    price: float,
    atr: float,
    cfg: TradingConfig,
) -> Dict[str, Any]:
    if not (_finite(price) and price > 0 and _finite(atr) and atr > 0):
        return {"side": None, "stop_px": None, "tp_px": None, "reason": "bad_price_or_atr"}

    tau_value = getattr(cfg, "tau", DEFAULT_TAU)
    if tau_value is None:
        return {"side": None, "stop_px": None, "tp_px": None, "reason": "ai_disabled"}

    try:
        tau = float(tau_value)
    except Exception:  # pragma: no cover - defensive
        tau = DEFAULT_TAU

    tau = max(0.0, min(1.0, tau))

    probs = _normalise_probs(proba)
    if probs is None:
        return {"side": None, "stop_px": None, "tp_px": None, "reason": "no_proba"}

    buy_p = probs["buy"]
    sell_p = probs["sell"]

    side: Optional[str]
    confidence = 0.0
    if buy_p >= tau and buy_p > sell_p:
        side = "buy"
        confidence = buy_p
    elif sell_p >= tau and sell_p > buy_p:
        side = "sell"
        confidence = sell_p
    else:
        return {"side": None, "stop_px": None, "tp_px": None, "reason": "below_tau"}

    k_sl = float(cfg.atr.k_sl)
    k_tp = float(cfg.atr.k_tp)

    if side == "buy":
        stop_px = price - k_sl * atr
        tp_px = price + k_tp * atr
        stop_pct = (price - stop_px) / price
    else:
        stop_px = price + k_sl * atr
        tp_px = price - k_tp * atr
        stop_pct = (stop_px - price) / price

    if not (_finite(stop_px) and _finite(tp_px)) or stop_pct < MIN_STOP_PCT:
        return {"side": None, "stop_px": None, "tp_px": None, "reason": "stop_too_close"}

    return {
        "side": side,
        "stop_px": stop_px,
        "tp_px": tp_px,
        "confidence": confidence,
        "tau": tau,
        "k_sl": k_sl,
        "k_tp": k_tp,
        "reason": "proba_pass",
    }


__all__ = ["make_signal"]
