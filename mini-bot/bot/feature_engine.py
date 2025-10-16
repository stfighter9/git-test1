"""Feature engineering utilities for the trading bot."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Iterable, List

from bot.state_store import Candle


@dataclass
class FeatureRow:
    ts_close: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    atr: float | None
    adx: float | None
    ret: float | None
    vol: float | None


def _sorted_candles(candles: Iterable[Candle]) -> List[Candle]:
    return sorted(list(candles), key=lambda c: c.ts_close)


def compute_features(candles: Iterable[Candle], atr_window: int = 14) -> List[FeatureRow]:
    rows = _sorted_candles(candles)
    if not rows:
        return []

    highs = [c.h for c in rows]
    lows = [c.l for c in rows]
    closes = [c.c for c in rows]

    true_range: List[float] = []
    plus_dm: List[float] = [0.0]
    minus_dm: List[float] = [0.0]
    returns: List[float | None] = [None]
    for i, candle in enumerate(rows):
        if i == 0:
            tr = candle.h - candle.l
            true_range.append(tr)
            continue
        prev_close = closes[i - 1]
        high = highs[i]
        low = lows[i]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_range.append(tr)
        up_move = high - highs[i - 1]
        down_move = lows[i - 1] - low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        returns.append((closes[i] - prev_close) / prev_close if prev_close else None)

    atr_values: List[float | None] = []
    plus_di_values: List[float | None] = []
    minus_di_values: List[float | None] = []
    adx_values: List[float | None] = []

    for i in range(len(rows)):
        if i + 1 < atr_window:
            atr_values.append(None)
            plus_di_values.append(None)
            minus_di_values.append(None)
            adx_values.append(None)
            continue
        tr_window = true_range[i + 1 - atr_window : i + 1]
        atr = sum(tr_window) / atr_window
        atr_values.append(atr)
        plus_sum = sum(plus_dm[i + 1 - atr_window : i + 1])
        minus_sum = sum(minus_dm[i + 1 - atr_window : i + 1])
        if atr == 0:
            plus_di = minus_di = None
        else:
            plus_di = 100 * plus_sum / atr
            minus_di = 100 * minus_sum / atr
        plus_di_values.append(plus_di)
        minus_di_values.append(minus_di)
        if plus_di is None or minus_di is None or (plus_di + minus_di) == 0:
            adx_values.append(None)
        else:
            dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
            if i + 1 < atr_window * 2:
                adx_window = [
                    abs(plus_di_values[j] - minus_di_values[j]) / (plus_di_values[j] + minus_di_values[j]) * 100
                    for j in range(max(atr_window - 1, 0), i + 1)
                    if plus_di_values[j] is not None
                    and minus_di_values[j] is not None
                    and (plus_di_values[j] + minus_di_values[j])
                ]
                adx_values.append(mean(adx_window) if adx_window else None)
            else:
                prev_adx = adx_values[-1]
                if prev_adx is None:
                    adx_values.append(dx)
                else:
                    adx_values.append((prev_adx * (atr_window - 1) + dx) / atr_window)

    vol_values: List[float | None] = []
    for i in range(len(rows)):
        if i + 1 < atr_window or returns[i] is None:
            vol_values.append(None)
            continue
        ret_window = [r for r in returns[i + 1 - atr_window : i + 1] if r is not None]
        if len(ret_window) < atr_window - 1:
            vol_values.append(None)
        else:
            vol_values.append(pstdev(ret_window))

    feature_rows: List[FeatureRow] = []
    for idx, candle in enumerate(rows):
        feature_rows.append(
            FeatureRow(
                ts_close=candle.ts_close,
                open=candle.o,
                high=candle.h,
                low=candle.l,
                close=candle.c,
                volume=candle.v,
                atr=atr_values[idx],
                adx=adx_values[idx],
                ret=returns[idx],
                vol=vol_values[idx],
            )
        )
    return feature_rows


__all__ = ["FeatureRow", "compute_features"]
