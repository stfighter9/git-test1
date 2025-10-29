from bot.market_guard import (
    SymbolMeta,
    round_price_for_side,
    round_qty_floor,
    sanitize_order,
)


def test_market_guard_rounding_direction() -> None:
    meta = SymbolMeta(price_increment=0.1, quantity_increment=0.001, min_notional=5.0, min_qty=0.001)
    buy_px = round_price_for_side(123.456, meta.price_increment, "buy")
    sell_px = round_price_for_side(123.456, meta.price_increment, "sell")
    assert buy_px == 123.4
    assert sell_px == 123.5
    qty = round_qty_floor(0.0504, meta.quantity_increment)
    assert qty == 0.05


def test_sanitize_order_auto_bump_min_notional() -> None:
    meta = SymbolMeta(price_increment=0.1, quantity_increment=0.01, min_notional=5.0, min_qty=0.01)
    px, qty, err = sanitize_order(meta, "buy", price=10.07, qty=0.2)
    assert err is None
    # buy prices floor down, quantities floor then auto-bump to clear min_notional
    assert px == 10.0
    assert qty == 0.5
    assert px * qty >= meta.min_notional


def test_sanitize_order_respects_manual_min_notional_block() -> None:
    meta = SymbolMeta(price_increment=0.5, quantity_increment=0.1, min_notional=50.0, min_qty=0.1)
    px, qty, err = sanitize_order(meta, "sell", price=25.1, qty=0.5, auto_bump_min_notional=False)
    assert px == 25.5  # sell orders round up
    assert qty == 0.5
    assert err == "min_notional"
