"""Simplified execution engine."""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from bot.config import TradingConfig
from bot.state_store import Order, Position, StateStore

LOGGER = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(self, ccxt_client, store: StateStore, cfg: TradingConfig) -> None:
        self.client = ccxt_client
        self.store = store
        self.cfg = cfg
        self._leverage_configured = False

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

    # ------------------------------------------------------------------
    def _ensure_leverage(self, symbol: str) -> None:
        if self._leverage_configured:
            return
        set_margin = getattr(self.client, "set_margin_mode", None)
        if callable(set_margin):
            try:  # pragma: no cover - network/exchange specific
                set_margin("isolated", symbol)
            except Exception as exc:
                LOGGER.warning("set_margin_mode failed: %s", exc)
        set_leverage = getattr(self.client, "set_leverage", None)
        if callable(set_leverage):
            try:  # pragma: no cover - network/exchange specific
                set_leverage(self.cfg.leverage, symbol)
            except Exception as exc:
                LOGGER.warning("set_leverage failed: %s", exc)
        self._leverage_configured = True

    def expire_orders(self, symbol: str, ttl_ms: int, now_ms: Optional[int] = None) -> int:
        if ttl_ms <= 0:
            return 0
        now_ms = now_ms or int(time.time() * 1000)
        expired = 0
        for order in self.store.list_orders(symbol):
            if not order.post_only:
                continue
            age = now_ms - order.ts_created
            if age < ttl_ms:
                continue
            try:
                self.client.cancel_order(order.oid, symbol=symbol)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.error("Failed to cancel stale order %s: %s", order.oid, exc)
                continue
            self.store.delete_order(order.oid)
            expired += 1
        return expired

    def submit_ladder(
        self,
        symbol: str,
        side: str,
        price: float,
        qty: float,
        stop_px: Optional[float] = None,
        tp_px: Optional[float] = None,
    ) -> List[str]:
        self._ensure_leverage(symbol)
        prices = self._ladder_prices(side, price)
        qty_per_order = qty / len(prices)
        order_ids: List[str] = []
        ts = int(time.time() * 1000)
        filled_qty = 0.0
        filled_value = 0.0
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
            status = str(order.get("status", "open")).lower()
            filled = float(order.get("filled", 0) or 0.0)
            is_filled = status == "closed" or filled >= qty_per_order
            self.store.upsert_order(
                Order(
                    oid=oid,
                    symbol=symbol,
                    side=side,
                    qty=qty_per_order,
                    px=level_price,
                    status="closed" if is_filled else "open",
                    ts_created=ts,
                    ts_updated=ts,
                    post_only=True,
                )
            )
            if is_filled:
                filled_qty += qty_per_order
                filled_value += qty_per_order * level_price
        if filled_qty >= max(qty * 0.999, qty - 1e-9):
            avg_px = filled_value / filled_qty if filled_qty else price
            self._establish_position(symbol, side, filled_qty, avg_px, stop_px, tp_px, ts)
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

    # ------------------------------------------------------------------
    def _establish_position(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_px: float,
        stop_px: Optional[float],
        tp_px: Optional[float],
        ts: int,
    ) -> None:
        position = Position(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_px=entry_px,
            sl_px=stop_px or 0.0,
            tp_px=tp_px or 0.0,
            leverage=self.cfg.leverage,
            ts_open=ts,
        )
        self.store.set_position(position)
        self._submit_protective_orders(symbol, side, qty, stop_px, tp_px)

    def _submit_protective_orders(
        self,
        symbol: str,
        side: str,
        qty: float,
        stop_px: Optional[float],
        tp_px: Optional[float],
    ) -> None:
        hedge_side = "sell" if side == "buy" else "buy"
        ts = int(time.time() * 1000)
        if stop_px and stop_px > 0:
            try:
                order = self.client.create_order(
                    symbol=symbol,
                    type="stop_market",
                    side=hedge_side,
                    amount=qty,
                    params={"stopPrice": stop_px, "reduceOnly": True},
                )
                oid = order.get("id") or order.get("clientOrderId") or f"stop-{ts}"
                self.store.upsert_order(
                    Order(
                        oid=oid,
                        symbol=symbol,
                        side=hedge_side,
                        qty=qty,
                        px=stop_px,
                        status=str(order.get("status", "open")),
                        ts_created=ts,
                        ts_updated=ts,
                        post_only=False,
                    )
                )
            except Exception as exc:  # pragma: no cover - protective best effort
                LOGGER.error("Failed to place stop order: %s", exc)
        if tp_px and tp_px > 0:
            try:
                order = self.client.create_order(
                    symbol=symbol,
                    type="limit",
                    side=hedge_side,
                    amount=qty,
                    price=tp_px,
                    params={"reduceOnly": True},
                )
                oid = order.get("id") or order.get("clientOrderId") or f"tp-{ts}"
                self.store.upsert_order(
                    Order(
                        oid=oid,
                        symbol=symbol,
                        side=hedge_side,
                        qty=qty,
                        px=tp_px,
                        status=str(order.get("status", "open")),
                        ts_created=ts,
                        ts_updated=ts,
                        post_only=False,
                    )
                )
            except Exception as exc:  # pragma: no cover - protective best effort
                LOGGER.error("Failed to place take-profit order: %s", exc)


__all__ = ["ExecutionEngine"]
