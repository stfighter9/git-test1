from types import SimpleNamespace

import pytest

from bot.funding import (
    FundingEvent,
    accrue_funding_inverse,
    accrue_funding_linear,
    estimate_annualized_funding,
)


def test_estimate_annualized_simple() -> None:
    ann = estimate_annualized_funding(0.0001, hours_window=8)
    assert pytest.approx(ann, rel=1e-6) == 0.0001 * (24 * 365 / 8)


def test_estimate_annualized_compounded_with_clamp() -> None:
    ann = estimate_annualized_funding(0.5, hours_window=8, method="compounded", clamp=1.0)
    assert -1.0 <= ann <= 1.0


def test_accrue_funding_linear_long_pays() -> None:
    position = SimpleNamespace(qty=0.01, side="buy")
    events: list[FundingEvent] = [(0.0001, 60000.0)]
    pnl = accrue_funding_linear(position, events)
    assert pytest.approx(pnl, rel=1e-6) == -0.06


def test_accrue_funding_linear_short_receives() -> None:
    position = SimpleNamespace(qty=0.01, side="sell")
    events: list[FundingEvent] = [(0.0001, 60000.0)]
    pnl = accrue_funding_linear(position, events)
    assert pytest.approx(pnl, rel=1e-6) == 0.06


def test_accrue_funding_linear_custom_convention() -> None:
    position = SimpleNamespace(qty=0.01, side="buy")
    events: list[FundingEvent] = [(0.0001, 60000.0)]
    pnl = accrue_funding_linear(position, events, long_pays_when_positive=False)
    assert pytest.approx(pnl, rel=1e-6) == 0.06


def test_accrue_funding_inverse() -> None:
    position = SimpleNamespace(qty=2, side="buy")
    events: list[FundingEvent] = [(0.0002, 30000.0)]
    pnl = accrue_funding_inverse(position, events, contract_size=100.0)
    assert pytest.approx(pnl, rel=1e-6) == -0.04


def test_zero_qty_noop() -> None:
    position = SimpleNamespace(qty=0.0, side="buy")
    pnl_linear = accrue_funding_linear(position, [(0.0001, 50000.0)])
    pnl_inverse = accrue_funding_inverse(position, [(0.0001, 50000.0)], contract_size=100.0)
    assert pnl_linear == 0.0
    assert pnl_inverse == 0.0

