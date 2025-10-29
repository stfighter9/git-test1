from pathlib import Path

import pytest

from bot.config import TradingConfig
from bot.market_guard import SymbolMeta
from bot.risk_guard import MarketConstraints, RiskGuard


DEFAULT_META = SymbolMeta(
    price_increment=0.1,
    quantity_increment=0.001,
    min_notional=10.0,
    min_qty=0.001,
)


def test_compute_qty_applies_buffers(tmp_path: Path) -> None:
    cfg = TradingConfig(risk_pct=0.01, fee_bp=10, slip_bp=10)
    guard = RiskGuard(cfg, freeze_path=tmp_path / "freeze.flag")
    qty = guard.compute_qty(nav=1000, price=20000, stop_px=19000)
    assert qty < 0.01  # buffers reduce size


def test_guard_signal_freezes_on_daily_loss(tmp_path: Path) -> None:
    guard = RiskGuard(TradingConfig(), freeze_path=tmp_path / "freeze.flag")
    qty, reason = guard.guard_signal(
        nav=1000,
        price=20000,
        stop_px=19000,
        constraints=MarketConstraints(min_qty=0.001, min_notional=10),
        daily_pnl_pct=-0.05,
        symbol_meta=DEFAULT_META,
        side="buy",
        available_quote=100_000,
    )
    assert qty is None
    assert reason == "daily_dd"
    assert guard.is_frozen()


def test_guard_signal_blocks_funding(tmp_path: Path) -> None:
    guard = RiskGuard(TradingConfig(), freeze_path=tmp_path / "freeze.flag")
    qty, reason = guard.guard_signal(
        nav=1000,
        price=20000,
        stop_px=19000,
        constraints=MarketConstraints(min_qty=0.001, min_notional=10),
        daily_pnl_pct=0.0,
        funding_annualized=1.0,
        symbol_meta=DEFAULT_META,
        side="buy",
        available_quote=1000,
    )
    assert qty is None
    assert reason == "funding_extreme"


def test_guard_signal_blocks_negative_funding(tmp_path: Path) -> None:
    guard = RiskGuard(TradingConfig(), freeze_path=tmp_path / "freeze.flag")
    qty, reason = guard.guard_signal(
        nav=1000,
        price=20000,
        stop_px=19000,
        constraints=MarketConstraints(min_qty=0.001, min_notional=10),
        daily_pnl_pct=0.0,
        funding_annualized=-1.0,
        symbol_meta=DEFAULT_META,
        side="buy",
        available_quote=1000,
    )
    assert qty is None
    assert reason == "funding_extreme"


def test_guard_signal_blocks_on_notify(tmp_path: Path) -> None:
    guard = RiskGuard(TradingConfig(), freeze_path=tmp_path / "freeze.flag")
    qty, reason = guard.guard_signal(
        nav=1000,
        price=20000,
        stop_px=19000,
        constraints=MarketConstraints(min_qty=0.001, min_notional=10),
        daily_pnl_pct=0.0,
        funding_annualized=0.0,
        notify_fail_streak=3,
        notify_threshold=3,
        symbol_meta=DEFAULT_META,
        side="buy",
        available_quote=1000,
    )
    assert qty is None
    assert reason == "notify_down"


def test_guard_signal_rejects_on_min_qty(tmp_path: Path) -> None:
    guard = RiskGuard(TradingConfig(), freeze_path=tmp_path / "freeze.flag")
    strict_meta = SymbolMeta(
        price_increment=0.1,
        quantity_increment=0.5,
        min_notional=10.0,
        min_qty=0.5,
    )
    qty, reason = guard.guard_signal(
        nav=100,
        price=20_000,
        stop_px=19_950,
        constraints=MarketConstraints(min_qty=0.5, min_notional=10.0),
        daily_pnl_pct=0.0,
        symbol_meta=strict_meta,
        side="buy",
        available_quote=1.0,
        leverage=1,
    )
    assert qty is None
    assert reason == "market_min_qty"


def test_compute_qty_caps_by_available_quote(tmp_path: Path) -> None:
    cfg = TradingConfig(risk_pct=0.1, leverage=2)
    guard = RiskGuard(cfg, freeze_path=tmp_path / "freeze.flag")
    qty = guard.compute_qty(
        nav=10_000,
        price=20_000,
        stop_px=19_000,
        available_quote=100.0,
        leverage=2,
    )
    assert qty == pytest.approx((100.0 * 2) / 20_000, rel=1e-6)


def test_guard_signal_auto_bumps_qty(tmp_path: Path) -> None:
    cfg = TradingConfig()
    guard = RiskGuard(cfg, freeze_path=tmp_path / "freeze.flag")
    qty, reason = guard.guard_signal(
        nav=1_000,
        price=20_000,
        stop_px=19_000,
        constraints=MarketConstraints(min_qty=0.001, min_notional=10),
        daily_pnl_pct=0.0,
        symbol_meta=DEFAULT_META,
        side="buy",
        available_quote=1_000,
    )
    assert reason is None
    assert qty >= DEFAULT_META.min_qty


def test_guard_signal_rejects_when_margin_insufficient(tmp_path: Path) -> None:
    cfg = TradingConfig(risk_pct=0.1, leverage=1)
    guard = RiskGuard(cfg, freeze_path=tmp_path / "freeze.flag")
    strict_meta = SymbolMeta(
        price_increment=0.1,
        quantity_increment=0.001,
        min_notional=500.0,
        min_qty=0.001,
    )
    qty, reason = guard.guard_signal(
        nav=5_000,
        price=20_000,
        stop_px=19_500,
        constraints=MarketConstraints(min_qty=0.001, min_notional=10),
        daily_pnl_pct=0.0,
        symbol_meta=strict_meta,
        side="buy",
        available_quote=50.0,
        leverage=1,
    )
    assert qty is None
    assert reason == "insufficient_margin"
