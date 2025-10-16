from __future__ import annotations

from unittest.mock import MagicMock

from bot.config import TradingConfig
from bot.execution import ExecutionEngine
from bot.state_store import Order, StateStore


def test_submit_ladder_creates_orders(temp_db) -> None:
    cfg = TradingConfig()
    client = MagicMock()
    client.create_order.side_effect = [
        {"id": "order1"},
        {"id": "order2"},
        {"id": "order3"},
    ]
    with StateStore(temp_db) as store:
        engine = ExecutionEngine(client, store, cfg)
        order_ids = engine.submit_ladder("BTC/USDT", "buy", price=20000, qty=0.03)
        assert order_ids == ["order1", "order2", "order3"]
        stored = store.list_orders("BTC/USDT")
        assert len(stored) == 3
        assert all(order.post_only for order in stored)


def test_cancel_all_removes_orders(temp_db) -> None:
    cfg = TradingConfig()
    client = MagicMock()
    with StateStore(temp_db) as store:
        engine = ExecutionEngine(client, store, cfg)
        store.upsert_order(
            Order(
                oid="x",
                symbol="BTC/USDT",
                side="buy",
                qty=0.01,
                px=20000,
                status="open",
                ts_created=1,
                ts_updated=1,
                post_only=True,
            )
        )
        engine.cancel_all("BTC/USDT")
        assert store.list_orders("BTC/USDT") == []
        client.cancel_order.assert_called_once_with("x", symbol="BTC/USDT")
