"""Execution engine with ladder handling and protective orders."""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from bot.config import TradingConfig
from bot.logger import jlog
from bot.market_guard import (
    SymbolMeta,
    round_price_for_side,
    round_qty_floor,
    round_to_step,
    sanitize_order,
)
from bot.state_store import Order, Position, StateStore
from bot.venue_adapter import order_params

LOGGER = logging.getLogger(__name__)


@dataclass
class LadderLevel:
    level: int
    price: float
    qty: float
    coid: str


class ExecutionEngine:
    def __init__(
        self,
        ccxt_client,
        store: StateStore,
        cfg: TradingConfig,
        log_path: str | Path | None = None,
    ) -> None:
        self.client = ccxt_client
        self.store = store
        self.cfg = cfg
        self._leverage_configured: Dict[str, bool] = {}
        self._symbol_meta: Dict[str, SymbolMeta] = {}
        self.log_path = str(log_path) if log_path else None

    # ------------------------------------------------------------------
    def _log_event(self, evt: str, **payload: object) -> None:
        if not self.log_path:
            return
        try:
            jlog(self.log_path, evt, **payload)
        except Exception as exc:  # pragma: no cover - logging best effort
            LOGGER.debug("jlog failure: %s", exc)

    # ------------------------------------------------------------------
    def _ladder_prices(self, side: str, price: float) -> List[float]:
        levels = max(self.cfg.order.ladder_levels, 1)
        step = 0.0005 * price
        prices = []
        for level in range(levels):
            offset = step * (level + 1)
            prices.append(price - offset if side == "buy" else price + offset)
        return prices

    def _hash_coid(self, seed: str) -> str:
        return hashlib.md5(seed.encode("utf8")).hexdigest()[:24]

    def _make_coid(self, symbol: str, side: str, level: int, ts: int) -> str:
        base = f"{symbol}|{side}|{level}|{ts}"
        return self._hash_coid(base)

    def _ensure_leverage(self, symbol: str) -> None:
        if self._leverage_configured.get(symbol):
            return
        set_margin = getattr(self.client, "set_margin_mode", None)
        if callable(set_margin):
            try:  # pragma: no cover - exchange specific
                set_margin("isolated", symbol)
            except Exception as exc:
                LOGGER.warning("set_margin_mode failed: %s", exc)
        set_leverage = getattr(self.client, "set_leverage", None)
        if callable(set_leverage):
            try:  # pragma: no cover - exchange specific
                set_leverage(self.cfg.leverage, symbol)
            except Exception as exc:
                LOGGER.warning("set_leverage failed: %s", exc)
        self._leverage_configured[symbol] = True

    def _load_symbol_meta(self, symbol: str) -> SymbolMeta:
        if symbol in self._symbol_meta:
            return self._symbol_meta[symbol]
        market = {}
        try:
            market = self.client.market(symbol)
        except Exception:  # pragma: no cover - fallback
            market = getattr(self.client, "markets", {}).get(symbol, {}) or {}
        precision = market.get("precision", {}) if isinstance(market, dict) else {}
        limits = market.get("limits", {}) if isinstance(market, dict) else {}
        info = market.get("info", {}) if isinstance(market, dict) else {}

        def step_from_precision(value: Optional[float]) -> Optional[float]:
            if value is None:
                return None
            try:
                return 10.0 ** (-float(value))
            except Exception:
                return None

        px_step = step_from_precision(precision.get("price"))
        qty_step = step_from_precision(precision.get("amount"))
        # fallbacks
        px_limit = (limits.get("price") or {}) if isinstance(limits, dict) else {}
        amt_limit = (limits.get("amount") or {}) if isinstance(limits, dict) else {}
        px_step = px_step or _coerce_float(px_limit.get("min")) or _coerce_float(info.get("tickSize")) or 0.01
        qty_step = qty_step or _coerce_float(amt_limit.get("min")) or _coerce_float(info.get("stepSize")) or 0.0001
        min_qty = _coerce_float(amt_limit.get("min")) or 0.0
        cost_limit = (limits.get("cost") or {}) if isinstance(limits, dict) else {}
        min_notional = _coerce_float(cost_limit.get("min")) or 0.0
        meta = SymbolMeta(
            price_increment=px_step,
            quantity_increment=qty_step,
            min_notional=min_notional,
            min_qty=min_qty,
        )
        self._symbol_meta[symbol] = meta
        return meta

    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        """Expose cached symbol metadata for collaborators (e.g. risk guard)."""

        return self._load_symbol_meta(symbol)

    # ------------------------------------------------------------------
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
            self._log_event(
                "order_expired",
                ts=now_ms,
                symbol=symbol,
                order_id=order.oid,
                client_order_id=order.client_order_id,
            )
            expired += 1
        return expired

    def cancel_all(self, symbol: str) -> None:
        for order in self.store.list_orders(symbol):
            try:
                self.client.cancel_order(order.oid, symbol=symbol)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.error("Failed to cancel order %s: %s", order.oid, exc)
                continue
            self.store.delete_order(order.oid)
            self._log_event(
                "order_cancel",
                ts=int(time.time() * 1000),
                symbol=symbol,
                order_id=order.oid,
                client_order_id=order.client_order_id,
                reason="manual_cancel",
            )

    # ------------------------------------------------------------------
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
        meta = self._load_symbol_meta(symbol)
        prices = self._ladder_prices(side, price)
        qty_per_order = qty / len(prices)
        ts = int(time.time() * 1000)
        levels: List[LadderLevel] = []
        for idx, level_price in enumerate(prices):
            coid = self._make_coid(symbol, side, idx, ts)
            px, level_qty, error = sanitize_order(meta, side, level_price, qty_per_order)
            if error:
                self.store.upsert_order(
                    Order(
                        oid=coid,
                        symbol=symbol,
                        side=side,
                        qty=level_qty,
                        px=px,
                        status="rejected",
                        ts_created=ts,
                        ts_updated=ts,
                        post_only=True,
                        client_order_id=coid,
                        maker=True,
                        fee=0.0,
                        reject_reason=error,
                    )
                )
                self._log_event(
                    "order_reject",
                    ts=ts,
                    symbol=symbol,
                    side=side,
                    price=px,
                    qty=level_qty,
                    client_order_id=coid,
                    reason=error,
                )
                continue
            levels.append(LadderLevel(level=idx, price=px, qty=level_qty, coid=coid))

        order_ids: List[str] = []
        filled_qty = 0.0
        filled_value = 0.0
        for level in levels:
            if self.store.get_order_by_coid(level.coid):
                LOGGER.debug("Skipping duplicate ladder level %s", level.coid)
                continue
            params = order_params(getattr(self.client, "id", ""), post_only=self.cfg.order.post_only)
            params = {**params, "clientOrderId": level.coid}
            self._log_event(
                "order_submit",
                ts=ts,
                symbol=symbol,
                side=side,
                price=level.price,
                qty=level.qty,
                client_order_id=level.coid,
                level=level.level,
            )
            try:
                order = self.client.create_order(
                    symbol=symbol,
                    type="limit",
                    side=side,
                    amount=level.qty,
                    price=level.price,
                    params=params,
                )
            except Exception as exc:  # pragma: no cover - best effort
                LOGGER.error("Order submission failed: %s", exc)
                self._log_event(
                    "order_error",
                    ts=ts,
                    symbol=symbol,
                    side=side,
                    price=level.price,
                    qty=level.qty,
                    client_order_id=level.coid,
                    reason="submit_error",
                )
                self.store.upsert_order(
                    Order(
                        oid=level.coid,
                        symbol=symbol,
                        side=side,
                        qty=level.qty,
                        px=level.price,
                        status="rejected",
                        ts_created=ts,
                        ts_updated=ts,
                        post_only=True,
                        client_order_id=level.coid,
                        maker=True,
                        fee=0.0,
                        reject_reason="submit_error",
                    )
                )
                continue
            oid = str(order.get("id") or order.get("clientOrderId") or level.coid)
            status_raw = str(order.get("status", "open")).lower()
            status = "open"
            if status_raw in {"closed", "filled"}:
                status = "closed"
            elif status_raw in {"canceled", "cancelled", "expired", "rejected"}:
                status = "canceled"
            filled = float(order.get("filled") or 0.0)
            avg_price = float(order.get("average") or order.get("price") or level.price)
            fee = 0.0
            fee_info = order.get("fee") or {}
            if isinstance(fee_info, dict):
                fee = float(fee_info.get("cost") or 0.0)
            info = order.get("info") if isinstance(order.get("info"), dict) else {}
            maker = True
            if isinstance(info, dict):
                taker_or_maker = info.get("takerOrMaker")
                if isinstance(taker_or_maker, str):
                    maker = taker_or_maker.lower() == "maker"
                elif "maker" in info:
                    maker = bool(info.get("maker"))
                elif "liquidity" in info:
                    maker = str(info.get("liquidity")).lower() == "maker"
            elif isinstance(order.get("postOnly"), bool):
                maker = bool(order.get("postOnly"))
            order_ids.append(oid)
            self.store.upsert_order(
                Order(
                    oid=oid,
                    symbol=symbol,
                    side=side,
                    qty=level.qty,
                    px=level.price,
                    status=status,
                    ts_created=ts,
                    ts_updated=ts,
                    post_only=True,
                    client_order_id=level.coid,
                    maker=maker,
                    fee=fee,
                    reject_reason=None,
                )
            )
            filled_amount = 0.0
            if status == "closed":
                filled_amount = filled or level.qty
            elif filled > 0:
                filled_amount = min(filled, level.qty)
            if filled_amount > 0:
                filled_qty += filled_amount
                filled_value += filled_amount * avg_price
                self._log_event(
                    "order_filled",
                    ts=int(time.time() * 1000),
                    symbol=symbol,
                    side=side,
                    qty=filled_amount,
                    price=avg_price,
                    order_id=oid,
                    client_order_id=level.coid,
                )
                continue
            fetch_order = getattr(self.client, "fetch_order", None)
            if callable(fetch_order):
                try:
                    fetched = fetch_order(oid, symbol=symbol)
                    f_status = str(fetched.get("status", "open")).lower()
                    f_filled = float(fetched.get("filled") or 0.0)
                    f_avg = float(fetched.get("average") or fetched.get("price") or level.price)
                    if f_status in {"closed", "filled"} or f_filled >= level.qty:
                        fill_amount = min(max(f_filled, level.qty), level.qty)
                        filled_qty += fill_amount
                        filled_value += fill_amount * f_avg
                        self.store.update_order_status(oid, "closed", int(time.time() * 1000))
                        self._log_event(
                            "order_filled",
                            ts=int(time.time() * 1000),
                            symbol=symbol,
                            side=side,
                            qty=fill_amount,
                            price=f_avg,
                            order_id=oid,
                            client_order_id=level.coid,
                        )
                except Exception as exc:  # pragma: no cover - network
                    LOGGER.warning("fetch_order failed for %s: %s", oid, exc)

        if filled_qty > 0:
            avg_px = filled_value / max(filled_qty, 1e-9)
            self._establish_position(symbol, side, filled_qty, avg_px, stop_px, tp_px)
        return order_ids

    # ------------------------------------------------------------------
    def _establish_position(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_px: float,
        stop_px: Optional[float],
        tp_px: Optional[float],
    ) -> None:
        ts = int(time.time() * 1000)
        meta = self._load_symbol_meta(symbol)
        qty = round_qty_floor(qty, meta.quantity_increment)
        entry_px = round_to_step(entry_px, meta.price_increment)
        stop_px = (
            round_price_for_side(stop_px, meta.price_increment, "sell" if side == "buy" else "buy")
            if stop_px
            else stop_px
        )
        tp_px = (
            round_price_for_side(tp_px, meta.price_increment, "sell" if side == "buy" else "buy")
            if tp_px
            else tp_px
        )

        existing = self.store.get_position(symbol)
        if existing:
            total_qty = round_qty_floor(existing.qty + qty, meta.quantity_increment)
            avg_px = (
                (existing.entry_px * existing.qty) + (entry_px * qty)
            ) / max(total_qty, 1e-9)
            existing.qty = total_qty
            existing.entry_px = avg_px
            if stop_px:
                existing.sl_px = stop_px
            if tp_px:
                existing.tp_px = tp_px
            sl_id, tp_id = self._submit_protective_orders(
                symbol,
                side,
                total_qty,
                existing.sl_px or stop_px,
                existing.tp_px or tp_px,
                existing=existing,
            )
            if sl_id:
                existing.sl_order_id = sl_id
            if tp_id:
                existing.tp_order_id = tp_id
            self.store.set_position(existing)
            return

        position = Position(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_px=entry_px,
            sl_px=stop_px or 0.0,
            tp_px=tp_px or 0.0,
            leverage=self.cfg.leverage,
            ts_open=ts,
            tp_order_id=None,
            sl_order_id=None,
            reduce_only=True,
            funding_pnl=0.0,
        )
        sl_id, tp_id = self._submit_protective_orders(
            symbol,
            side,
            qty,
            stop_px,
            tp_px,
            existing=None,
        )
        position.sl_order_id = sl_id
        position.tp_order_id = tp_id
        self.store.set_position(position)

    def _submit_protective_orders(
        self,
        symbol: str,
        side: str,
        qty: float,
        stop_px: Optional[float],
        tp_px: Optional[float],
        existing: Optional[Position] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        hedge_side = "sell" if side == "buy" else "buy"
        sl_id: Optional[str] = None
        tp_id: Optional[str] = None
        params_reduce = order_params(
            getattr(self.client, "id", ""),
            post_only=False,
            reduce_only=True,
            trigger="mark",
        )
        meta = self._load_symbol_meta(symbol)
        qty = round_qty_floor(qty, meta.quantity_increment)

        def cancel_existing(order_id: Optional[str]) -> None:
            if not order_id:
                return
            try:
                self.client.cancel_order(order_id, symbol=symbol)
                self._log_event(
                    "order_cancel",
                    ts=int(time.time() * 1000),
                    symbol=symbol,
                    order_id=order_id,
                    reason="replace_protective",
                )
            except Exception as exc:  # pragma: no cover - best effort
                LOGGER.debug("Failed to cancel protective order %s: %s", order_id, exc)
            self.store.delete_order(order_id)

        if existing:
            cancel_existing(existing.sl_order_id)
            cancel_existing(existing.tp_order_id)

        ts = int(time.time() * 1000)
        if stop_px and stop_px > 0:
            stop_px = round_price_for_side(stop_px, meta.price_increment, hedge_side)
            stop_params = {**params_reduce, "clientOrderId": self._hash_coid(f"{symbol}|sl|{ts}")}
            try:
                order = self.client.create_order(
                    symbol=symbol,
                    type="stop_market",
                    side=hedge_side,
                    amount=qty,
                    params={**stop_params, "stopPrice": stop_px},
                )
                sl_id = str(order.get("id") or order.get("clientOrderId") or self._hash_coid(f"sl|{ts}"))
                created_ts = int(time.time() * 1000)
                self.store.upsert_order(
                    Order(
                        oid=sl_id,
                        symbol=symbol,
                        side=hedge_side,
                        qty=qty,
                        px=stop_px,
                        status=str(order.get("status", "open")),
                        ts_created=created_ts,
                        ts_updated=created_ts,
                        post_only=False,
                        client_order_id=order.get("clientOrderId") or stop_params["clientOrderId"],
                        maker=False,
                        fee=0.0,
                        reject_reason=None,
                    )
                )
                self._log_event(
                    "protective_submit",
                    ts=created_ts,
                    symbol=symbol,
                    side=hedge_side,
                    price=stop_px,
                    qty=qty,
                    order_id=sl_id,
                    kind="stop",
                )
            except Exception as exc:  # pragma: no cover - protective best effort
                LOGGER.error("Failed to place stop order: %s", exc)
        if tp_px and tp_px > 0:
            tp_px = round_price_for_side(tp_px, meta.price_increment, hedge_side)
            tp_params = {**params_reduce, "clientOrderId": self._hash_coid(f"{symbol}|tp|{ts}")}
            try:
                order = self.client.create_order(
                    symbol=symbol,
                    type="limit",
                    side=hedge_side,
                    amount=qty,
                    price=tp_px,
                    params=tp_params,
                )
                tp_id = str(order.get("id") or order.get("clientOrderId") or self._hash_coid(f"tp|{ts}"))
                created_ts = int(time.time() * 1000)
                self.store.upsert_order(
                    Order(
                        oid=tp_id,
                        symbol=symbol,
                        side=hedge_side,
                        qty=qty,
                        px=tp_px,
                        status=str(order.get("status", "open")),
                        ts_created=created_ts,
                        ts_updated=created_ts,
                        post_only=False,
                        client_order_id=order.get("clientOrderId") or tp_params["clientOrderId"],
                        maker=False,
                        fee=0.0,
                        reject_reason=None,
                    )
                )
                self._log_event(
                    "protective_submit",
                    ts=created_ts,
                    symbol=symbol,
                    side=hedge_side,
                    price=tp_px,
                    qty=qty,
                    order_id=tp_id,
                    kind="take_profit",
                )
            except Exception as exc:  # pragma: no cover - protective best effort
                LOGGER.error("Failed to place take-profit order: %s", exc)
        return sl_id, tp_id


def _coerce_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["ExecutionEngine"]
