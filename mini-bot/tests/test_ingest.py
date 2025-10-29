from __future__ import annotations

import time

from bot.data_ingest import fetch_candles, ingest_cycle, timeframe_to_seconds
from bot.state_store import StateStore


class DummyClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0
        self.kwargs = []

    def fetch_ohlcv(self, symbol, timeframe, limit=None, since=None):
        self.calls += 1
        self.kwargs.append({"symbol": symbol, "timeframe": timeframe, "limit": limit, "since": since})
        return self.rows


def test_fetch_candles_filters_open_bar(monkeypatch):
    now = int(time.time() * 1000)
    rows = [
        [now - 3 * 14400 * 1000, 1, 2, 0.5, 1.5, 10],
        [now - 2 * 14400 * 1000, 1.5, 2.5, 1.0, 2.0, None],
        [now - 14400 * 1000, 2.0, 2.5, 1.5, 2.2, 12],
        [now + 1000, 2.5, 3.0, 2.0, 2.6, 13],
    ]
    client = DummyClient(rows)
    candles = fetch_candles(client, "BTC/USDT", "4h", n=10)
    assert len(candles) == 3
    tf_ms = timeframe_to_seconds("4h") * 1000
    assert candles[0].ts_close == ((rows[0][0] // tf_ms) * tf_ms) + tf_ms
    assert candles[1].v == 0.0  # None volume coerced to zero
    assert all(c.ts_close <= int(time.time() * 1000) for c in candles)


def test_ingest_cycle_upserts_latest(temp_db, monkeypatch):
    now = int(time.time() * 1000)
    rows = [
        [now - 5 * 14400 * 1000, 1, 2, 0.5, 1.5, 10],
        [now - 4 * 14400 * 1000, 1.5, 2.5, 1.0, 2.0, 11],
        [now - 3 * 14400 * 1000, 2.0, 2.8, 1.8, 2.4, 12],
        [now - 2 * 14400 * 1000, 2.4, 3.0, 2.1, 2.8, 13],
        [now - 14400 * 1000, 2.8, 3.2, 2.4, 3.0, 14],
    ]
    client = DummyClient(rows)
    with StateStore(temp_db) as store:
        inserted = ingest_cycle(client, store, "BTC/USDT", "4h")
        assert len(inserted) == 3
        fetched = store.get_last_n_candles("BTC/USDT", "4h", 3)
        tf_ms = timeframe_to_seconds("4h") * 1000
        expected = [((r[0] // tf_ms) * tf_ms) + tf_ms for r in rows[-4:-1]]
        assert [c.ts_close for c in fetched] == expected
        assert client.kwargs[-1]["since"] is None

        # Subsequent ingest should request incremental window
        ingest_cycle(client, store, "BTC/USDT", "4h")
        assert client.kwargs[-1]["since"] == expected[-1] - tf_ms
