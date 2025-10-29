"""Exchange specific parameter helpers."""
from __future__ import annotations

from typing import Dict, Optional


def order_params(
    venue: str,
    *,
    post_only: bool = True,
    reduce_only: bool = False,
    trigger: str = "mark",
    market_type: Optional[str] = None,
) -> Dict[str, object]:
    venue_norm = (venue or "").lower()
    trigger_norm = (trigger or "mark").lower()
    market_type_norm = (market_type or "").lower()

    params: Dict[str, object] = {}

    if venue_norm in {"binance", "binanceusdm", "binancecoinm"}:
        is_futures = venue_norm in {"binanceusdm", "binancecoinm"} or market_type_norm in {
            "linear",
            "inverse",
            "perpetual",
            "futures",
        }
        if post_only:
            params["postOnly"] = True
            if is_futures:
                params["timeInForce"] = "GTX"
        if reduce_only:
            params["reduceOnly"] = True
        if trigger_norm:
            if trigger_norm == "mark":
                params["workingType"] = "MARK_PRICE"
            elif trigger_norm == "index":
                params["workingType"] = "INDEX_PRICE"
            else:
                params["workingType"] = "CONTRACT_PRICE"
    elif venue_norm in {"bybit", "bybitlinear"}:
        if post_only:
            params["postOnly"] = True
        if reduce_only:
            params["reduce_only"] = True
        if trigger_norm:
            if trigger_norm == "index":
                params["triggerBy"] = "IndexPrice"
            elif trigger_norm == "last":
                params["triggerBy"] = "LastPrice"
            else:
                params["triggerBy"] = "MarkPrice"
    elif venue_norm in {"okx"}:
        if post_only:
            params["ordType"] = "post_only"
        if reduce_only:
            params["reduceOnly"] = True
        if trigger_norm:
            if trigger_norm not in {"mark", "last", "index"}:
                trigger_norm = "mark"
            params["triggerPxType"] = trigger_norm
    else:
        if post_only:
            params["postOnly"] = True
        if reduce_only:
            params["reduceOnly"] = True
    return params


__all__ = ["order_params"]
