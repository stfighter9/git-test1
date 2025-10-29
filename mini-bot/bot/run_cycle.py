"""Main orchestration loop for a single trading cycle."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Mapping, Optional, Protocol

from bot.config import TradingConfig, load_config
from bot.data_ingest import ingest_cycle, timeframe_to_seconds
from bot.execution import ExecutionEngine
from bot.feature_engine import compute_features
from bot.funding import estimate_annualized_funding
from bot.logger import jlog
from bot.model_infer import ModelInferer
from bot.notifier import TelegramNotifier
from bot.regime import allow_trade
from bot.risk_guard import MarketConstraints, RiskGuard
from bot.signal_policy import make_signal
from bot.state_store import DailyNav, StateStore

LOGGER = logging.getLogger(__name__)


class ProbabilisticModel(Protocol):
    def predict_proba(self, feature_row: Mapping[str, float]) -> Optional[Mapping[str, float]]:
        ...


def _regime_state_path(store: StateStore) -> Path:
    base = Path(getattr(store, "db_path", Path("data/mini.db")))
    return base.with_suffix(".regime.state")


def _load_prev_regime_allowed(store: StateStore) -> Optional[bool]:
    path = _regime_state_path(store)
    if not path.exists():
        return None
    try:
        text = path.read_text().strip()
    except OSError:
        return None
    if text == "1":
        return True
    if text == "0":
        return False
    return None


def _store_regime_allowed(store: StateStore, allowed: bool) -> None:
    path = _regime_state_path(store)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1" if allowed else "0")
    except OSError:
        LOGGER.debug("Failed to persist regime state at %s", path)


def _quote_currency(symbol: str) -> str:
    if ":" in symbol:
        candidate = symbol.split(":")[-1]
    else:
        parts = symbol.split("/")
        candidate = parts[1] if len(parts) > 1 else symbol
    if "/" in candidate:
        candidate = candidate.split("/")[-1]
    return candidate


def _can_notify(notifier: TelegramNotifier) -> bool:
    return bool(getattr(notifier, "token", None) and getattr(notifier, "chat_id", None))


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


def _current_utc_day_start(now_ms: int) -> int:
    dt = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    start = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000)


def _ensure_daily_nav_snapshot(store: StateStore, nav: float, now_ms: int) -> float:
    day_ts = _current_utc_day_start(now_ms)
    existing = store.get_daily_nav(day_ts)
    if existing:
        return existing.nav
    store.upsert_daily_nav(
        DailyNav(ts=day_ts, nav=nav, trading_pnl=0.0, fees_pnl=0.0, funding_pnl=0.0)
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
    inferer: ProbabilisticModel,
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
        if _can_notify(notifier):
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
    predict_fn = getattr(inferer, "predict_proba", None)
    if callable(predict_fn):
        try:
            proba = predict_fn(feature_map)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Model inference failed: %s", exc)
            proba = None
    else:
        LOGGER.warning("Inferer missing predict_proba; skipping model step")
        proba = None
    proba_map = proba or {"buy": 0.0, "sell": 0.0}
    signal = make_signal(proba_map, price=last.close, atr=last.atr or 0.0, cfg=cfg)

    if signal["side"] is None:
        return {"status": "no_signal"}

    log_path = "experiments/live/cycles.jsonl"
    atr_pct = (last.atr or 0.0) / last.close if last.close else 0.0
    prev_regime = _load_prev_regime_allowed(store)
    regime_allowed, regime_reason = allow_trade(
        adx=last.adx,
        atr_pct=atr_pct,
        adx_min=cfg.regime.adx_min,
        atr_pct_min=cfg.regime.atr_pct_min,
        atr_pct_max=cfg.regime.atr_pct_max,
        prev_allowed=prev_regime,
    )
    _store_regime_allowed(store, regime_allowed)
    if not regime_allowed:
        jlog(
            log_path,
            "regime_block",
            ts=now_ms,
            symbol=symbol,
            reason=regime_reason,
        )
        return {"status": "regime_blocked", "reason": regime_reason}

    position = store.get_position(symbol)
    open_positions = 1 if position else 0
    engine = ExecutionEngine(ccxt_client, store, cfg, log_path=log_path)
    ttl_ms = cfg.order.timeout_bars * timeframe_to_seconds(timeframe) * 1000
    engine.expire_orders(symbol, ttl_ms, now_ms=now_ms)

    guard = RiskGuard(cfg)
    market = getattr(ccxt_client, "markets", {}).get(symbol, {})
    constraints = _market_constraints(market)
    symbol_meta = engine.get_symbol_meta(symbol)
    funding_annualized = None
    fetch_funding = getattr(ccxt_client, "fetch_funding_rate", None)
    if callable(fetch_funding):
        try:
            data = fetch_funding(symbol)  # pragma: no cover - network
            rate = float(data.get("fundingRate", 0.0))
            funding_annualized = estimate_annualized_funding(rate)
        except Exception as exc:  # pragma: no cover
            LOGGER.debug("fetch_funding_rate failed: %s", exc)
    notify_threshold = getattr(notifier, "max_failures_allowed", 3)
    available_quote = nav
    balance_fetch = getattr(ccxt_client, "fetch_balance", None)
    if callable(balance_fetch):
        try:
            balance = balance_fetch()
            quote_ccy = _quote_currency(symbol)
            free_balances = balance.get("free", {}) if isinstance(balance, dict) else {}
            total_balances = balance.get("total", {}) if isinstance(balance, dict) else {}
            available_quote = (
                free_balances.get(quote_ccy)
                or total_balances.get(quote_ccy)
                or available_quote
            )
        except Exception as exc:  # pragma: no cover - balance fetch best effort
            LOGGER.debug("fetch_balance failed: %s", exc)

    qty, freeze_reason = guard.guard_signal(
        nav,
        last.close,
        signal["stop_px"],
        constraints,
        daily_pnl_pct,
        funding_annualized=funding_annualized,
        notify_fail_streak=notifier.failure_streak,
        notify_threshold=notify_threshold,
        symbol_meta=symbol_meta,
        side=signal["side"],
        available_quote=available_quote,
        leverage=cfg.leverage,
        open_positions=open_positions,
    )
    if qty is None:
        jlog(
            log_path,
            "risk_block",
            ts=now_ms,
            symbol=symbol,
            reason=freeze_reason,
        )
        if freeze_reason == "max_positions":
            return {"status": "max_position"}
        return {"status": "risk_blocked", "reason": freeze_reason}

    order_ids = engine.submit_ladder(
        symbol,
        signal["side"],
        last.close,
        qty,
        stop_px=signal.get("stop_px"),
        tp_px=signal.get("tp_px"),
    )

    if _can_notify(notifier):
        notifier.send_message(
            f"Signal: {signal['side']} qty={qty:.6f} price={last.close:.2f} orders={len(order_ids)}"
        )

    jlog(
        log_path,
        "cycle",
        ts=now_ms,
        symbol=symbol,
        p_buy=proba_map["buy"],
        p_sell=proba_map["sell"],
        tau=cfg.tau,
        k_tp=cfg.atr.k_tp,
        k_sl=cfg.atr.k_sl,
        policy_verdict=signal["side"],
        risk_reason=None,
        order_ids=order_ids,
        freeze=guard.is_frozen(),
        regime_reason=regime_reason,
    )

    return {"status": "ok", "orders": order_ids, "signal": signal}


def main() -> dict:
    cfg = load_config()
    try:
        model = ModelInferer()
    except Exception as exc:  # pragma: no cover - allows rule-only mode
        LOGGER.warning("Model unavailable, running in rule-only mode: %s", exc)

        class _NullInferer:
            def predict_proba(self, *_args, **_kwargs):
                return None

        model = _NullInferer()
    trading_cfg = cfg.trading
    notifier = TelegramNotifier(
        token=None,
        chat_id=None,
        max_failures=cfg.monitoring.telegram.fail_freeze_threshold,
    )
    db_path = Path("data/mini.db")

    # Placeholder ccxt client for main entry point.
    try:
        import ccxt  # type: ignore

        client = getattr(ccxt, trading_cfg.venue.name)({"enableRateLimit": True})
    except Exception as exc:  # pragma: no cover - environment dependent
        LOGGER.error("Unable to instantiate ccxt client: %s", exc)
        raise

    with StateStore(db_path) as store:
        quote_ccy = _quote_currency(trading_cfg.symbol)
        balance = getattr(client, "fetch_balance", lambda: {"total": {quote_ccy: 0}})()
        nav = balance.get("total", {}).get(quote_ccy, 0.0)
        now_ms = _utc_now_ms()
        open_nav = _ensure_daily_nav_snapshot(store, nav, now_ms)
        daily_pnl_pct = _compute_daily_pnl_pct(open_nav, nav)
        return run_once(client, store, trading_cfg, model, notifier, nav, daily_pnl_pct)


if __name__ == "__main__":  # pragma: no cover
    main()
