"""Main orchestration loop for a single trading cycle."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from bot.config import TradingConfig, load_config
from bot.data_ingest import ingest_cycle, timeframe_to_seconds
from bot.execution import ExecutionEngine
from bot.feature_engine import compute_features
from bot.model_infer import ModelInferer
from bot.notifier import TelegramNotifier
from bot.risk_guard import MarketConstraints, RiskGuard
from bot.signal_policy import make_signal
from bot.state_store import LedgerEntry, StateStore

LOGGER = logging.getLogger(__name__)


def _market_constraints(market: Dict) -> MarketConstraints:
    limits = market.get("limits", {}) if market else {}
    amount = limits.get("amount", {}) if isinstance(limits, dict) else {}
    cost = limits.get("cost", {}) if isinstance(limits, dict) else {}
    return MarketConstraints(
        min_qty=float(amount.get("min", 0) or 0),
        min_notional=float(cost.get("min", 0) or 0),
    )


def _utc_now_ms() -> int:
    return int(time.time() * 1000)


def _current_utc_day(now_ms: int) -> str:
    return datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).date().isoformat()


def _ensure_daily_nav_snapshot(store: StateStore, nav: float, now_ms: int) -> float:
    day_key = _current_utc_day(now_ms)
    for entry in store.list_ledger_entries(limit=50):
        if entry.type == "nav_snapshot" and entry.meta == day_key:
            return float(entry.amount)
    store.insert_ledger_entry(
        LedgerEntry(ts=now_ms, type="nav_snapshot", amount=nav, meta=day_key)
    )
    return nav


def _compute_daily_pnl_pct(open_nav: float, current_nav: float) -> float:
    if open_nav <= 0:
        return 0.0
    return (current_nav - open_nav) / open_nav


def run_once(
    ccxt_client,
    store: StateStore,
    cfg: TradingConfig,
    inferer: ModelInferer,
    notifier: TelegramNotifier,
    nav: float,
    daily_pnl_pct: Optional[float] = None,
) -> dict:
    symbol = cfg.symbol
    timeframe = cfg.timeframe
    now_ms = _utc_now_ms()
    open_nav = _ensure_daily_nav_snapshot(store, nav, now_ms)
    if daily_pnl_pct is None:
        daily_pnl_pct = _compute_daily_pnl_pct(open_nav, nav)

    try:
        candles = ingest_cycle(ccxt_client, store, symbol, timeframe)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Ingest failed: %s", exc)
        notifier.send_message(f"Ingest failed: {exc}")
        return {"error": str(exc)}

    history = store.get_last_n_candles(symbol, timeframe, cfg.atr.window * 5)
    if not history:
        return {"status": "no_candles"}

    features = compute_features(history, atr_window=cfg.atr.window)
    if not features:
        return {"status": "no_features"}

    last = features[-1]
    feature_map = {"atr": last.atr or 0.0, "adx": last.adx or 0.0, "ret": last.ret or 0.0, "vol": last.vol or 0.0}
    proba = inferer.predict_proba(feature_map)
    signal = make_signal(proba, price=last.close, atr=last.atr or 0.0, cfg=cfg)

    if signal["side"] is None:
        return {"status": "no_signal"}

    if cfg.max_positions <= 1 and store.get_position(symbol):
        return {"status": "max_position"}

    engine = ExecutionEngine(ccxt_client, store, cfg)
    ttl_ms = cfg.order.timeout_bars * timeframe_to_seconds(timeframe) * 1000
    engine.expire_orders(symbol, ttl_ms, now_ms=now_ms)

    guard = RiskGuard(cfg)
    market = getattr(ccxt_client, "markets", {}).get(symbol, {})
    constraints = _market_constraints(market)
    qty = guard.guard_signal(nav, last.close, signal["stop_px"], constraints, daily_pnl_pct)
    if qty is None:
        return {"status": "risk_blocked"}

    order_ids = engine.submit_ladder(
        symbol,
        signal["side"],
        last.close,
        qty,
        stop_px=signal.get("stop_px"),
        tp_px=signal.get("tp_px"),
    )

    notifier.send_message(
        f"Signal: {signal['side']} qty={qty:.6f} price={last.close:.2f} orders={len(order_ids)}"
    )

    return {"status": "ok", "orders": order_ids, "signal": signal}


def main() -> dict:
    cfg = load_config()
    trading_cfg = cfg.trading
    model = ModelInferer()
    notifier = TelegramNotifier(token=None, chat_id=None)
    db_path = Path("data/mini.db")

    # Placeholder ccxt client for main entry point.
    try:
        import ccxt  # type: ignore

        client = getattr(ccxt, trading_cfg.venue.name)({"enableRateLimit": True})
    except Exception as exc:  # pragma: no cover - environment dependent
        LOGGER.error("Unable to instantiate ccxt client: %s", exc)
        raise

    with StateStore(db_path) as store:
        balance = getattr(client, "fetch_balance", lambda: {"total": {"USDT": 0}})()
        nav = balance.get("total", {}).get("USDT", 0.0)
        now_ms = _utc_now_ms()
        open_nav = _ensure_daily_nav_snapshot(store, nav, now_ms)
        daily_pnl_pct = _compute_daily_pnl_pct(open_nav, nav)
        return run_once(client, store, trading_cfg, model, notifier, nav, daily_pnl_pct)


if __name__ == "__main__":  # pragma: no cover
    main()
