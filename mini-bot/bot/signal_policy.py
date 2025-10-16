"""Signal policy derived from model probabilities."""
from __future__ import annotations

from typing import Mapping, Optional

from bot.config import DEFAULT_TAU, TradingConfig


def make_signal(
    proba: Mapping[str, float],
    price: float,
    atr: float,
    cfg: TradingConfig,
) -> dict[str, Optional[float | str]]:
    tau = getattr(cfg, "tau", DEFAULT_TAU)
    buy_p = float(proba.get("buy", 0.0))
    sell_p = float(proba.get("sell", 0.0))

    if price <= 0 or atr is None or atr <= 0:
        return {"side": None, "stop_px": None, "tp_px": None}

    side: Optional[str]
    if buy_p >= tau and buy_p > sell_p:
        side = "buy"
    elif sell_p >= tau and sell_p > buy_p:
        side = "sell"
    else:
        side = None

    if side is None:
        return {"side": None, "stop_px": None, "tp_px": None}

    k_sl = cfg.atr.k_sl
    k_tp = cfg.atr.k_tp

    if side == "buy":
        stop_px = price - k_sl * atr
        tp_px = price + k_tp * atr
    else:
        stop_px = price + k_sl * atr
        tp_px = price - k_tp * atr

    return {"side": side, "stop_px": stop_px, "tp_px": tp_px}


__all__ = ["make_signal"]
