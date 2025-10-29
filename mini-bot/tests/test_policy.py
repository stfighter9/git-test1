from __future__ import annotations

from bot.config import TradingConfig
from bot.signal_policy import make_signal


def test_make_signal_buy_side() -> None:
    cfg = TradingConfig()
    signal = make_signal({"buy": 0.8, "sell": 0.2}, price=20000, atr=100, cfg=cfg)
    assert signal["side"] == "buy"
    assert signal["stop_px"] == 20000 - cfg.atr.k_sl * 100
    assert signal["tp_px"] == 20000 + cfg.atr.k_tp * 100
    assert signal["reason"] == "proba_pass"
    assert signal["confidence"] > signal["tau"]


def test_make_signal_sell_side() -> None:
    cfg = TradingConfig()
    signal = make_signal({"buy": 0.3, "sell": 0.75}, price=20000, atr=120, cfg=cfg)
    assert signal["side"] == "sell"
    assert signal["stop_px"] == 20000 + cfg.atr.k_sl * 120
    assert signal["tp_px"] == 20000 - cfg.atr.k_tp * 120
    assert signal["confidence"] > signal["tau"]


def test_make_signal_none_when_below_tau() -> None:
    cfg = TradingConfig(tau=0.7)
    signal = make_signal({"buy": 0.65, "sell": 0.4}, price=20000, atr=100, cfg=cfg)
    assert signal["side"] is None
    assert signal["reason"] == "below_tau"


def test_make_signal_handles_missing_proba() -> None:
    cfg = TradingConfig()
    signal = make_signal(None, price=20000, atr=100, cfg=cfg)
    assert signal["side"] is None
    assert signal["reason"] == "no_proba"


def test_make_signal_rejects_bad_inputs() -> None:
    cfg = TradingConfig()
    signal = make_signal({"buy": 0.9, "sell": 0.1}, price=-1, atr=100, cfg=cfg)
    assert signal["side"] is None
    assert signal["reason"] == "bad_price_or_atr"
