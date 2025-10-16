from __future__ import annotations

from bot.config import TradingConfig
from bot.signal_policy import make_signal


def test_make_signal_buy_side() -> None:
    cfg = TradingConfig()
    signal = make_signal({"buy": 0.8, "sell": 0.2}, price=20000, atr=100, cfg=cfg)
    assert signal["side"] == "buy"
    assert signal["stop_px"] == 20000 - cfg.atr.k_sl * 100
    assert signal["tp_px"] == 20000 + cfg.atr.k_tp * 100


def test_make_signal_sell_side() -> None:
    cfg = TradingConfig()
    signal = make_signal({"buy": 0.3, "sell": 0.75}, price=20000, atr=120, cfg=cfg)
    assert signal["side"] == "sell"
    assert signal["stop_px"] == 20000 + cfg.atr.k_sl * 120
    assert signal["tp_px"] == 20000 - cfg.atr.k_tp * 120


def test_make_signal_none_when_below_tau() -> None:
    cfg = TradingConfig(tau=0.7)
    signal = make_signal({"buy": 0.65, "sell": 0.4}, price=20000, atr=100, cfg=cfg)
    assert signal["side"] is None
