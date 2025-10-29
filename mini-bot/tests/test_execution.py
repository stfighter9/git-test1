from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bot.config import TradingConfig
from bot.execution import ExecutionEngine
from bot.state_store import Order, Position, StateStore


@pytest.fixture()
def mock_client() -> MagicMock:
    client = MagicMock()
    client.id = "binance"
    client.market.return_value = {
        "precision": {"price": 2, "amount": 3},
        "limits": {"amount": {"min": 0.001}, "cost": {"min": 5}},
    }
    return client


def test_execution_idempotent(monkeypatch, mock_client, temp_db) -> None:
    cfg = TradingConfig()
    with StateStore(temp_db) as store:
        engine = ExecutionEngine(mock_client, store, cfg)
        ts_ms = 1000
        monkeypatch.setattr("bot.execution.time.time", lambda: ts_ms / 1000)
        prices = engine._ladder_prices("buy", 20000)
        for level, price in enumerate(prices):
            coid = engine._make_coid("BTC/USDT", "buy", level, ts_ms)
            store.upsert_order(
                Order(
                    oid=f"existing-{level}",
                    symbol="BTC/USDT",
                    side="buy",
                    qty=0.01,
                    px=price,
                    status="open",
                    ts_created=ts_ms,
                    ts_updated=ts_ms,
                    post_only=True,
                    client_order_id=coid,
                    maker=True,
                    fee=0.0,
                    reject_reason=None,
                )
            )
        mock_client.create_order.return_value = {"id": "o1", "status": "open", "filled": 0}
        engine.submit_ladder("BTC/USDT", "buy", price=20000, qty=0.03)
        assert mock_client.create_order.call_count == 0


def test_partial_fill_sets_protection(mock_client, temp_db) -> None:
    cfg = TradingConfig()
    mock_client.create_order.side_effect = [
        {"id": "order1", "status": "closed", "filled": 0.01},
        {"id": "order2", "status": "open", "filled": 0},
        {"id": "order3", "status": "open", "filled": 0},
        {"id": "stop1", "status": "open", "clientOrderId": "sl"},
        {"id": "tp1", "status": "open", "clientOrderId": "tp"},
    ]
    with StateStore(temp_db) as store:
        engine = ExecutionEngine(mock_client, store, cfg)
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
        assert position.sl_px == 19500
        assert position.tp_px == 21000
        orders = store.list_orders("BTC/USDT")
        assert any(o.post_only is False for o in orders)


def test_protective_orders_reconciled_on_additional_fill(mock_client, temp_db) -> None:
    cfg = TradingConfig()
    cfg.order.ladder_levels = 1
    mock_client.create_order.side_effect = [
        {"id": "limit1", "status": "closed", "filled": 0.01},
        {"id": "stop-new", "status": "open", "clientOrderId": "sl-new"},
        {"id": "tp-new", "status": "open", "clientOrderId": "tp-new"},
    ]
    mock_client.cancel_order = MagicMock()
    with StateStore(temp_db) as store:
        position = Order(
            oid="sl-old",
            symbol="BTC/USDT",
            side="sell",
            qty=0.01,
            px=19500,
            status="open",
            ts_created=0,
            ts_updated=0,
            post_only=False,
            client_order_id="sl-old",
            maker=False,
            fee=0.0,
            reject_reason=None,
        )
        store.upsert_order(position)
        store.upsert_order(
            Order(
                oid="tp-old",
                symbol="BTC/USDT",
                side="sell",
                qty=0.01,
                px=21000,
                status="open",
                ts_created=0,
                ts_updated=0,
                post_only=False,
                client_order_id="tp-old",
                maker=False,
                fee=0.0,
                reject_reason=None,
            )
        )
        store.set_position(
            Position(
                symbol="BTC/USDT",
                side="buy",
                qty=0.01,
                entry_px=20000,
                sl_px=19500,
                tp_px=21000,
                leverage=cfg.leverage,
                ts_open=0,
                tp_order_id="tp-old",
                sl_order_id="sl-old",
                reduce_only=True,
                funding_pnl=0.0,
            )
        )
        engine = ExecutionEngine(mock_client, store, cfg)
        engine.submit_ladder(
            "BTC/USDT",
            "buy",
            price=20000,
            qty=0.01,
            stop_px=19500,
            tp_px=21000,
        )
        pos = store.get_position("BTC/USDT")
        assert pos is not None
        assert pos.qty > 0.01
        assert pos.sl_order_id == "stop-new"
        assert pos.tp_order_id == "tp-new"
        mock_client.cancel_order.assert_any_call("sl-old", symbol="BTC/USDT")
        mock_client.cancel_order.assert_any_call("tp-old", symbol="BTC/USDT")


def test_expire_orders_marks_stale(mock_client, temp_db) -> None:
    cfg = TradingConfig()
    with StateStore(temp_db) as store:
        engine = ExecutionEngine(mock_client, store, cfg)
        store.upsert_order(
            Order(
                oid="x",
                symbol="BTC/USDT",
                side="buy",
                qty=0.01,
                px=20000,
                status="open",
                ts_created=0,
                ts_updated=0,
                post_only=True,
                client_order_id="coid-x",
                maker=True,
                fee=0.0,
                reject_reason=None,
            )
        )
        engine.expire_orders("BTC/USDT", ttl_ms=1, now_ms=2000)
        assert store.list_orders("BTC/USDT") == []
