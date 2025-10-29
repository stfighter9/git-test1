from __future__ import annotations

import math

from bot.regime import allow_trade


def test_allow_trade_rejects_nan() -> None:
    allowed, reason = allow_trade(math.nan, 0.3)
    assert not allowed
    assert reason == "err:adx_nan"


def test_allow_trade_hysteresis() -> None:
    allowed, reason = allow_trade(30.0, 0.3, adx_min=25.0, atr_pct_min=0.2, atr_pct_max=0.8)
    assert allowed and reason == "enter"

    allowed2, reason2 = allow_trade(
        24.5,
        0.31,
        adx_min=25.0,
        atr_pct_min=0.2,
        atr_pct_max=0.8,
        prev_allowed=True,
    )
    assert allowed2 and reason2 == "keep"

    allowed3, reason3 = allow_trade(
        20.0,
        0.31,
        adx_min=25.0,
        atr_pct_min=0.2,
        atr_pct_max=0.8,
        prev_allowed=True,
    )
    assert not allowed3 and reason3 == "exit:adx_drop"
