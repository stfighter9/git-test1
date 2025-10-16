from __future__ import annotations

import csv
from pathlib import Path

from bot.config import TradingConfig
from bot.notifier import TelegramNotifier
from bot.run_cycle import run_once
from bot.state_store import StateStore

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

    def fetch_ohlcv(self, symbol, timeframe, limit):
        rows = []
        with FIXTURE_PATH.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(
                    [
                        int(row["ts_close"]),
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row["volume"]),
                    ]
                )
        return rows

    def create_order(self, **kwargs):
        return {"id": f"order-{kwargs['price']:.2f}"}


class DummyInferer:
    def predict_proba(self, feature_row):
        return {"buy": 0.8, "sell": 0.2}


def test_run_once_places_orders(tmp_path: Path) -> None:
    cfg = TradingConfig()
    client = DummyClient()
    notifier = TelegramNotifier(None, None, freeze_path=tmp_path / "notify.freeze")
    inferer = DummyInferer()
    with StateStore(tmp_path / "test.db") as store:
        result = run_once(
            client,
            store,
            cfg,
            inferer,  # type: ignore[arg-type]
            notifier,
            nav=1000.0,
            daily_pnl_pct=0.0,
        )
    assert result["status"] == "ok"
    assert len(result["orders"]) == cfg.order.ladder_levels
