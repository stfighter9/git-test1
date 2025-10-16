from __future__ import annotations

from unittest.mock import MagicMock

from bot.config import TradingConfig
from bot.execution import ExecutionEngine
from bot.state_store import Order, StateStore


def test_submit_ladder_creates_orders(temp_db) -> None:
    cfg = TradingConfig()
    client = MagicMock()
    client.set_margin_mode = MagicMock()
    client.set_leverage = MagicMock()
    client.create_order.side_effect = [
        {"id": "order1", "status": "open"},
        {"id": "order2", "status": "open"},
        {"id": "order3", "status": "open"},
    ]
    with StateStore(temp_db) as store:
        engine = ExecutionEngine(client, store, cfg)
        order_ids = engine.submit_ladder("BTC/USDT", "buy", price=20000, qty=0.03)
        assert order_ids == ["order1", "order2", "order3"]
        stored = store.list_orders("BTC/USDT")
        assert len(stored) == 3
        assert all(order.post_only for order in stored)
    client.set_margin_mode.assert_called_once_with("isolated", "BTC/USDT")
    client.set_leverage.assert_called_once()


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


def test_expire_orders_cancels_stale(temp_db) -> None:
    cfg = TradingConfig()
    client = MagicMock()
    with StateStore(temp_db) as store:
        engine = ExecutionEngine(client, store, cfg)
        store.upsert_order(
            Order(
                oid="old",
                symbol="BTC/USDT",
                side="buy",
                qty=0.01,
                px=20000,
                status="open",
                ts_created=0,
                ts_updated=0,
                post_only=True,
            )
        )
        expired = engine.expire_orders("BTC/USDT", ttl_ms=1, now_ms=2000)
        assert expired == 1
        assert store.list_orders("BTC/USDT") == []
    client.cancel_order.assert_called_once_with("old", symbol="BTC/USDT")


def test_submit_ladder_sets_position_and_protection(temp_db) -> None:
    cfg = TradingConfig()
    client = MagicMock()
    client.set_margin_mode = MagicMock()
    client.set_leverage = MagicMock()
    client.create_order.side_effect = [
        {"id": "order1", "status": "closed"},
        {"id": "order2", "status": "closed"},
        {"id": "order3", "status": "closed"},
        {"id": "stop1", "status": "open"},
        {"id": "tp1", "status": "open"},
    ]
    with StateStore(temp_db) as store:
        engine = ExecutionEngine(client, store, cfg)
        engine.submit_ladder(
            "BTC/USDT",
            "buy",
            price=20000,
            qty=0.03,
            stop_px=19500,
            tp_px=21000,
        )
        position = store.get_position("BTC/USDT")
        assert position is not None
        assert position.side == "buy"
        assert position.sl_px == 19500
        assert position.tp_px == 21000
        orders = store.list_orders("BTC/USDT")
        # 3 ladder + 2 protective orders
        assert len(orders) == 5
        assert any(not order.post_only for order in orders)
    assert client.create_order.call_count == 5
