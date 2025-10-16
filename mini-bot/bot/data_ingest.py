"""Market data ingestion via ccxt REST."""
from __future__ import annotations

import logging
import time
from typing import List

from bot.state_store import Candle, StateStore

LOGGER = logging.getLogger(__name__)


_TIMEFRAME_TO_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


def _timeframe_to_seconds(tf: str) -> int:
    if tf not in _TIMEFRAME_TO_SECONDS:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return _TIMEFRAME_TO_SECONDS[tf]


def _filter_closed_candles(candles: List[List[float]], tf_seconds: int) -> List[List[float]]:
    cutoff_ms = int(time.time() * 1000) - tf_seconds * 1000
    return [c for c in candles if int(c[0]) <= cutoff_ms]


def fetch_candles(ccxt_client, symbol: str, tf: str, n: int = 300) -> List[Candle]:
    """Fetch closed candles from the exchange."""
    tf_seconds = _timeframe_to_seconds(tf)
    attempt = 0
    last_error: Exception | None = None
    while attempt < 3:
        try:
            raw = ccxt_client.fetch_ohlcv(symbol, timeframe=tf, limit=n)
            closed = _filter_closed_candles(raw, tf_seconds)
            candles = [
                Candle(
                    symbol=symbol,
                    tf=tf,
                    ts_close=int(row[0]),
                    o=float(row[1]),
                    h=float(row[2]),
                    l=float(row[3]),
                    c=float(row[4]),
                    v=float(row[5]),
                )
                for row in closed
            ]
            return candles
        except Exception as exc:  # pragma: no cover - defensive log
            last_error = exc
            sleep_time = 2**attempt
            LOGGER.warning("fetch_ohlcv failed (attempt=%s): %s", attempt + 1, exc)
            time.sleep(sleep_time)
            attempt += 1
    raise RuntimeError("fetch_candles failed") from last_error


def ingest_cycle(ccxt_client, store: StateStore, symbol: str, tf: str) -> List[Candle]:
    """Fetch and persist the most recent closed candles."""
    tf_seconds = _timeframe_to_seconds(tf)
    candles = fetch_candles(ccxt_client, symbol, tf)
    candles = sorted(candles, key=lambda c: c.ts_close)
    if not candles:
        LOGGER.warning("No candles fetched for symbol=%s tf=%s", symbol, tf)
        return []

    cutoff_ms = int(time.time() * 1000) - tf_seconds * 1000
    closed = [c for c in candles if c.ts_close <= cutoff_ms]
    if len(closed) < 3:
        LOGGER.warning("Missing candles for symbol=%s tf=%s count=%s", symbol, tf, len(closed))
    latest = closed[-3:]

    store.upsert_candles(closed)
    return latest


__all__ = ["fetch_candles", "ingest_cycle"]
