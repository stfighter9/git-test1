"""Helpers for respecting exchange tick/step and notional constraints."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_UP, getcontext
from typing import Optional, Tuple


getcontext().prec = 28


@dataclass
class SymbolMeta:
    price_increment: float
    quantity_increment: float
    min_notional: float
    min_qty: float


def _quantize(value: float, step: float, mode) -> float:
    if step <= 0:
        return float(value)
    v = Decimal(str(value))
    s = Decimal(str(step))
    q = (v / s).to_integral_value(rounding=mode) * s
    return float(q)


def round_price_for_side(price: float, step: float, side: str) -> float:
    """Round prices respecting side direction so we never worsen the quote."""

    side_normalized = (side or "").lower()
    if side_normalized == "buy":
        return _quantize(price, step, ROUND_DOWN)
    if side_normalized == "sell":
        return _quantize(price, step, ROUND_UP)
    return _quantize(price, step, ROUND_DOWN)


def round_qty_floor(qty: float, step: float) -> float:
    """Floor quantities to the permitted step."""

    return _quantize(qty, step, ROUND_DOWN)


def round_to_step(value: float, step: float) -> float:
    """Round to the nearest step using decimal quantisation (compat helper)."""

    return _quantize(value, step, ROUND_HALF_EVEN)


def sanitize_order(
    symbol_meta: SymbolMeta,
    side: str,
    price: float,
    qty: float,
    auto_bump_min_notional: bool = True,
) -> Tuple[float, float, Optional[str]]:
    """Return rounded price/qty and an error string if constraints are violated."""

    if price <= 0 or qty <= 0:
        return price, qty, "invalid"

    px = round_price_for_side(price, symbol_meta.price_increment, side)
    amount = round_qty_floor(qty, symbol_meta.quantity_increment)

    if amount <= 0:
        return px, amount, "min_qty"

    if amount < symbol_meta.min_qty:
        bumped = round_qty_floor(symbol_meta.min_qty, symbol_meta.quantity_increment)
        if bumped <= 0:
            return px, amount, "min_qty"
        amount = bumped

    notional = px * amount
    if notional < symbol_meta.min_notional:
        if not auto_bump_min_notional or px <= 0:
            return px, amount, "min_notional"
        needed = Decimal(str(symbol_meta.min_notional)) / Decimal(str(px))
        bumped_qty = _quantize(float(needed), symbol_meta.quantity_increment, ROUND_UP)
        if bumped_qty <= amount:
            bumped_qty = amount
        amount = bumped_qty
        if px * amount < symbol_meta.min_notional:
            return px, amount, "min_notional"

    max_qty = getattr(symbol_meta, "max_qty", None)
    if max_qty is not None and amount > float(max_qty):
        return px, amount, "max_qty"

    max_price = getattr(symbol_meta, "max_price", None)
    if max_price is not None and px > float(max_price):
        return px, amount, "max_price"

    return px, amount, None


__all__ = [
    "SymbolMeta",
    "round_price_for_side",
    "round_qty_floor",
    "round_to_step",
    "sanitize_order",
]
