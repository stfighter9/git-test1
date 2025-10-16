from __future__ import annotations

from pathlib import Path

import pytest

from bot.config import TradingConfig
from bot.risk_guard import MarketConstraints, RiskGuard


def test_position_size_respects_risk(tmp_path: Path) -> None:
    cfg = TradingConfig(risk_pct=0.01)
    guard = RiskGuard(cfg, freeze_path=tmp_path / "freeze.flag")
    qty = guard.position_size(nav=1000, price=20000, stop_px=19000)
    assert pytest.approx(qty, rel=1e-6) == 0.01


def test_guard_signal_freezes_on_daily_loss(tmp_path: Path) -> None:
    freeze = tmp_path / "freeze.flag"
    guard = RiskGuard(TradingConfig(), freeze_path=freeze)
    qty = guard.guard_signal(
        nav=1000,
        price=20000,
        stop_px=19000,
        constraints=MarketConstraints(min_qty=0.001, min_notional=10),
        daily_pnl_pct=-0.04,
    )
    assert qty is None
    assert guard.is_frozen()


def test_guard_signal_rejects_small_qty(tmp_path: Path) -> None:
    freeze = tmp_path / "freeze.flag"
    guard = RiskGuard(TradingConfig(), freeze_path=freeze)
    qty = guard.guard_signal(
        nav=1000,
        price=20000,
        stop_px=19900,
        constraints=MarketConstraints(min_qty=0.2, min_notional=5000),
        daily_pnl_pct=0.0,
    )
    assert qty is None
