"""Simplified execution engine."""
from __future__ import annotations

import logging
import time
from typing import List

from bot.config import TradingConfig
from bot.state_store import Order, StateStore

LOGGER = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(self, ccxt_client, store: StateStore, cfg: TradingConfig) -> None:
        self.client = ccxt_client
        self.store = store
        self.cfg = cfg

    def _ladder_prices(self, side: str, price: float) -> List[float]:
        levels = max(self.cfg.order.ladder_levels, 1)
        step = 0.0005 * price
        prices = []
        for level in range(levels):
            offset = step * (level + 1)
            if side == "buy":
                prices.append(price - offset)
            else:
                prices.append(price + offset)
        return prices

    def submit_ladder(self, symbol: str, side: str, price: float, qty: float) -> List[str]:
        prices = self._ladder_prices(side, price)
        qty_per_order = qty / len(prices)
        order_ids: List[str] = []
        ts = int(time.time() * 1000)
        for level_price in prices:
            params = {"postOnly": True}
            try:
                order = self.client.create_order(
                    symbol=symbol,
                    type="limit",
                    side=side,
                    amount=qty_per_order,
                    price=level_price,
                    params=params,
                )
            except Exception as exc:  # pragma: no cover
                LOGGER.error("Order submission failed: %s", exc)
                continue
            oid = order.get("id") or order.get("clientOrderId")
            if not oid:
                LOGGER.warning("Order missing id: %s", order)
                continue
            order_ids.append(oid)
            self.store.upsert_order(
                Order(
                    oid=oid,
                    symbol=symbol,
                    side=side,
                    qty=qty_per_order,
                    px=level_price,
                    status="open",
                    ts_created=ts,
                    ts_updated=ts,
                    post_only=True,
                )
            )
        return order_ids

    def cancel_all(self, symbol: str) -> None:
        orders = self.store.list_orders(symbol)
        for order in orders:
            try:
                self.client.cancel_order(order.oid, symbol=symbol)
            except Exception as exc:  # pragma: no cover
                LOGGER.error("Failed to cancel order %s: %s", order.oid, exc)
                continue
            self.store.delete_order(order.oid)


__all__ = ["ExecutionEngine"]
