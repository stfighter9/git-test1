from __future__ import annotations

from pathlib import Path

from bot.state_store import Candle, LedgerEntry, Order, Position, StateStore


def test_upsert_and_get_candles(temp_db: Path) -> None:
    candles = [
        Candle(symbol="BTC/USDT", tf="4h", ts_close=1, o=1, h=2, l=0.5, c=1.5, v=10),
        Candle(symbol="BTC/USDT", tf="4h", ts_close=2, o=1.5, h=2.5, l=1.0, c=2.0, v=12),
    ]
    with StateStore(temp_db) as store:
        store.upsert_candles(candles)
        fetched = store.get_last_n_candles("BTC/USDT", "4h", 2)
    assert fetched == candles


def test_order_crud(temp_db: Path) -> None:
    order = Order(
        oid="abc",
        symbol="BTC/USDT",
        side="buy",
        qty=1.0,
        px=20000.0,
        status="new",
        ts_created=100,
        ts_updated=100,
        post_only=True,
    )
    with StateStore(temp_db) as store:
        store.upsert_order(order)
        loaded = store.get_order("abc")
        assert loaded == order
        store.update_order_status("abc", "filled", 200)
        loaded = store.get_order("abc")
        assert loaded.status == "filled"
        assert loaded.ts_updated == 200
        store.delete_order("abc")
        assert store.get_order("abc") is None


def test_position_set_get_clear(temp_db: Path) -> None:
    position = Position(
        symbol="BTC/USDT",
        side="long",
        qty=1.0,
        entry_px=20000.0,
        sl_px=19000.0,
        tp_px=21000.0,
        leverage=3.0,
        ts_open=100,
    )
    with StateStore(temp_db) as store:
        store.set_position(position)
        loaded = store.get_position("BTC/USDT")
        assert loaded == position
        store.clear_position("BTC/USDT")
        assert store.get_position("BTC/USDT") is None


def test_ledger_insert_and_list(temp_db: Path) -> None:
    entry = LedgerEntry(ts=1, type="pnl", amount=10.0, meta="test")
    with StateStore(temp_db) as store:
        store.insert_ledger_entry(entry)
        entries = store.list_ledger_entries()
    assert entries == [entry]


def test_pragmas_applied(temp_db: Path) -> None:
    with StateStore(temp_db) as store:
        cur = store.conn.execute("PRAGMA journal_mode;")
        mode = cur.fetchone()[0]
    assert mode.lower() == "wal"
