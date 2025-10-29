from __future__ import annotations

import csv
from pathlib import Path

from bot.feature_engine import FeatureRow, compute_features
from bot.state_store import Candle

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "candles_sample.csv"


def load_candles() -> list[Candle]:
    candles: list[Candle] = []
    with FIXTURE_PATH.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append(
                Candle(
                    symbol="BTC/USDT",
                    tf="4h",
                    ts_close=int(row["ts_close"]),
                    o=float(row["open"]),
                    h=float(row["high"]),
                    l=float(row["low"]),
                    c=float(row["close"]),
                    v=float(row["volume"]),
                )
            )
    return candles


def test_compute_features_returns_ordered_rows() -> None:
    candles = load_candles()
    rows = compute_features(candles, atr_window=5)
    assert [r.ts_close for r in rows] == sorted(r.ts_close for r in rows)
    assert len(rows) == len(candles)


def test_compute_features_matches_golden_sample() -> None:
    candles = load_candles()
    rows = compute_features(candles, atr_window=5)
    last = rows[-1]
    assert isinstance(last, FeatureRow)
    assert round(last.atr or 0, 2) == 600.0
    assert round(last.adx or 0, 2) == 100.0
    assert round(last.ret or 0, 6) == 0.007538
    assert round(last.vol or 0, 6) == 0.000984


def test_compute_features_empty_returns_empty() -> None:
    assert compute_features([], atr_window=5) == []
