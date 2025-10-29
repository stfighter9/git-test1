from __future__ import annotations

import csv
from pathlib import Path

import csv
from pathlib import Path

from bot.config import TradingConfig
from bot.data_ingest import timeframe_to_seconds
from bot.notifier import TelegramNotifier
from bot.run_cycle import run_once
from bot.state_store import Position, StateStore

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "candles_sample.csv"


class DummyClient:
    def __init__(self):
        self.markets = {
            "BTC/USDT:USDT": {
                "limits": {
                    "amount": {"min": 0.001},
                    "cost": {"min": 10},
                }
            }
        }
        self.cancelled = []
        self.margin_mode_calls = []
        self.leverage_calls = []

    def market(self, symbol):
        return self.markets.get(symbol, {})

    def fetch_ohlcv(self, symbol, timeframe, limit=None, since=None):
        rows = []
        tf_ms = timeframe_to_seconds(timeframe) * 1000
        with FIXTURE_PATH.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts_close = int(row["ts_close"])
                rows.append(
                    [
                        ts_close - tf_ms,
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row["volume"]),
                    ]
                )
        return rows

    def create_order(self, **kwargs):
        price = kwargs.get("price")
        if price is None:
            stop_price = kwargs.get("params", {}).get("stopPrice", 0.0)
            price = stop_price
        return {
            "id": f"order-{float(price):.2f}",
            "status": kwargs.get("status", "open"),
            "filled": kwargs.get("amount", 0),
        }

    def cancel_order(self, oid, symbol=None):
        self.cancelled.append((oid, symbol))

    def set_margin_mode(self, mode, symbol):
        self.margin_mode_calls.append((mode, symbol))

    def set_leverage(self, leverage, symbol):
        self.leverage_calls.append((leverage, symbol))

    def fetch_funding_rate(self, symbol):
        return {"fundingRate": 0.0}


class DummyInferer:
    def predict_proba(self, feature_row):
        return {"buy": 0.8, "sell": 0.2}


def test_run_once_places_orders(tmp_path: Path) -> None:
    cfg = TradingConfig()
    cfg.regime.adx_min = 0
    cfg.regime.atr_pct_min = 0
    cfg.regime.atr_pct_max = 10
    client = DummyClient()
    notifier = TelegramNotifier(
        None,
        None,
        freeze_path=tmp_path / "notify.freeze",
        max_failures=3,
    )
    inferer = DummyInferer()
    with StateStore(tmp_path / "test.db") as store:
        result = run_once(
            client,
            store,
            cfg,
            inferer,  # type: ignore[arg-type]
            notifier,
            nav=1000.0,
        )
    assert result["status"] == "ok"
    assert len(result["orders"]) == cfg.order.ladder_levels
    assert client.margin_mode_calls
    assert client.leverage_calls


def test_run_once_respects_max_position(tmp_path: Path) -> None:
    cfg = TradingConfig()
    cfg.regime.adx_min = 0
    cfg.regime.atr_pct_min = 0
    cfg.regime.atr_pct_max = 10
    client = DummyClient()
    notifier = TelegramNotifier(
        None,
        None,
        freeze_path=tmp_path / "notify.freeze",
        max_failures=3,
    )
    inferer = DummyInferer()
    with StateStore(tmp_path / "test.db") as store:
        store.set_position(
            Position(
                symbol=cfg.symbol,
                side="buy",
                qty=0.01,
                entry_px=20000,
                sl_px=19000,
                tp_px=21000,
                leverage=cfg.leverage,
                ts_open=0,
            )
        )
        result = run_once(
            client,
            store,
            cfg,
            inferer,  # type: ignore[arg-type]
            notifier,
            nav=1000.0,
        )
    assert result["status"] == "max_position"
