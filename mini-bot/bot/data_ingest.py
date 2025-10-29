"""Market data ingestion via ccxt REST."""
from __future__ import annotations

import logging
import time

from bot.state_store import Candle, StateStore

LOGGER = logging.getLogger(__name__)


TIMEFRAME_TO_SECONDS = {
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


def timeframe_to_seconds(tf: str) -> int:
    if tf not in TIMEFRAME_TO_SECONDS:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return TIMEFRAME_TO_SECONDS[tf]


def _normalize_timestamp(ts_ms: int, tf_seconds: int) -> int:
    """Normalize a timestamp down to the open time of its candle."""

    step_ms = tf_seconds * 1000
    if step_ms <= 0:
        return ts_ms
    return (ts_ms // step_ms) * step_ms


def _filter_closed_candles(
    candles: list[list[float]], tf_seconds: int, *, now_ms: int | None = None
) -> list[list[float]]:
    """Return only candles whose close timestamp is in the past."""

    if now_ms is None:
        now_ms = int(time.time() * 1000)
    step_ms = tf_seconds * 1000
    return [c for c in candles if int(c[0]) + step_ms <= now_ms]


def fetch_candles(
    ccxt_client,
    symbol: str,
    tf: str,
    n: int = 300,
    *,
    since: int | None = None,
) -> list[Candle]:
    """Fetch closed candles from the exchange."""
    tf_seconds = timeframe_to_seconds(tf)
    step_ms = tf_seconds * 1000
    attempt = 0
    last_error: Exception | None = None
    while attempt < 3:
        try:
            kwargs = {"timeframe": tf, "limit": n}
            if since is not None:
                kwargs["since"] = int(since)
            raw = ccxt_client.fetch_ohlcv(symbol, **kwargs)
            now_ms = int(time.time() * 1000)
            closed = _filter_closed_candles(raw, tf_seconds, now_ms=now_ms)
            candles: list[Candle] = []
            for row in closed:
                ts_open = _normalize_timestamp(int(row[0]), tf_seconds)
                ts_close = ts_open + step_ms
                vol_raw = row[5] if len(row) > 5 else 0.0
                volume = float(vol_raw) if vol_raw not in (None, "") else 0.0
                candles.append(
                    Candle(
                        symbol=symbol,
                        tf=tf,
                        ts_close=ts_close,
                        o=float(row[1]),
                        h=float(row[2]),
                        l=float(row[3]),
                        c=float(row[4]),
                        v=volume,
                    )
                )
            return candles
        except Exception as exc:  # pragma: no cover - defensive log
            last_error = exc
            sleep_time = 2**attempt
            LOGGER.warning("fetch_ohlcv failed (attempt=%s): %s", attempt + 1, exc)
            time.sleep(sleep_time)
            attempt += 1
    raise RuntimeError("fetch_candles failed") from last_error


def ingest_cycle(ccxt_client, store: StateStore, symbol: str, tf: str) -> list[Candle]:
    """Fetch and persist the most recent closed candles."""
    tf_seconds = timeframe_to_seconds(tf)
    step_ms = tf_seconds * 1000
    last = store.get_last_n_candles(symbol, tf, 1)
    since: int | None = None
    if last:
        last_close = last[0].ts_close
        since = max(0, last_close - step_ms)
    candles = fetch_candles(ccxt_client, symbol, tf, since=since)
    candles = sorted(candles, key=lambda c: c.ts_close)
    if not candles:
        LOGGER.warning("No candles fetched for symbol=%s tf=%s", symbol, tf)
        return []

    cutoff_ms = int(time.time() * 1000) - step_ms
    closed = [c for c in candles if c.ts_close <= cutoff_ms]
    if len(closed) < 3:
        LOGGER.warning("Missing candles for symbol=%s tf=%s count=%s", symbol, tf, len(closed))
    latest = closed[-3:]

    store.upsert_candles(closed)
    LOGGER.info(
        "Ingested %s closed candles (%s..%s) for %s %s",
        len(closed),
        closed[0].ts_close if closed else None,
        closed[-1].ts_close if closed else None,
        symbol,
        tf,
    )
    return latest


__all__ = ["TIMEFRAME_TO_SECONDS", "fetch_candles", "ingest_cycle", "timeframe_to_seconds"]
