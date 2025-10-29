"""Risk management helpers."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Optional, Tuple

from bot.config import TradingConfig
from bot.market_guard import SymbolMeta, sanitize_order


@dataclass
class MarketConstraints:
    min_qty: float
    min_notional: float


MIN_STOP_PCT = 0.001  # 0.1% stop distance safeguard


class RiskGuard:
    def __init__(
        self,
        cfg: TradingConfig,
        freeze_path: Path | str = Path("data/freeze.flag"),
    ) -> None:
        self.cfg = cfg
        self.freeze_path = Path(freeze_path)

    # Freeze management -------------------------------------------------
    def is_frozen(self) -> bool:
        return self.freeze_path.exists()

    def set_frozen(self, frozen: bool) -> None:
        if frozen:
            self.freeze_path.parent.mkdir(parents=True, exist_ok=True)
            self.freeze_path.write_text("frozen")
        elif self.freeze_path.exists():
            self.freeze_path.unlink()

    # Position sizing ---------------------------------------------------
    def compute_stop_pct(self, price: float, stop_px: float) -> float:
        if not (isfinite(price) and isfinite(stop_px)):
            return 0.0
        if price <= 0 or stop_px <= 0:
            return 0.0
        return abs(price - stop_px) / price

    def compute_qty(
        self,
        nav: float,
        price: float,
        stop_px: float,
        fee_bp: float | None = None,
        slip_bp: float | None = None,
        *,
        available_quote: float | None = None,
        leverage: float | None = None,
    ) -> float:
        stop_pct = self.compute_stop_pct(price, stop_px)
        if stop_pct <= 0 or stop_pct < MIN_STOP_PCT:
            return 0.0
        if not isfinite(nav) or nav <= 0:
            return 0.0
        fee_bp = self.cfg.fee_bp if fee_bp is None else fee_bp
        slip_bp = self.cfg.slip_bp if slip_bp is None else slip_bp
        buffer = 1.0 - max(0.0, (fee_bp + slip_bp)) / 10000.0
        buffer = min(1.0, max(0.8, buffer))
        risk_notional = nav * self.cfg.risk_pct * buffer
        qty = risk_notional / (stop_pct * max(price, 1e-12))
        qty = max(qty, 0.0)

        lev = self.cfg.leverage if leverage is None else leverage
        if available_quote is not None and lev and lev > 0:
            max_notional = max(0.0, available_quote) * float(lev)
            qty_cap = max_notional / max(price, 1e-12)
            qty = min(qty, qty_cap)

        return qty

    # Daily loss limit --------------------------------------------------
    def should_freeze(
        self,
        daily_pnl_pct: float,
        funding_annualized: Optional[float] = None,
        notify_fail_streak: int = 0,
        notify_threshold: Optional[int] = None,
    ) -> Optional[str]:
        if daily_pnl_pct <= -self.cfg.daily_loss_limit_pct:
            return "daily_dd"
        if (
            funding_annualized is not None
            and abs(funding_annualized) > self.cfg.funding.extreme_annualized
        ):
            return "funding_extreme"
        if notify_threshold is not None and notify_fail_streak >= notify_threshold:
            return "notify_down"
        return None

    # Market constraints ------------------------------------------------
    def respects_constraints(self, qty: float, price: float, constraints: MarketConstraints) -> bool:
        if qty < constraints.min_qty:
            return False
        if qty * price < constraints.min_notional:
            return False
        return True

    def guard_signal(
        self,
        nav: float,
        price: float,
        stop_px: float,
        constraints: MarketConstraints,
        daily_pnl_pct: float,
        funding_annualized: Optional[float] = None,
        notify_fail_streak: int = 0,
        notify_threshold: Optional[int] = None,
        *,
        symbol_meta: Optional[SymbolMeta] = None,
        side: Optional[str] = None,
        available_quote: Optional[float] = None,
        leverage: Optional[float] = None,
        open_positions: int = 0,
    ) -> Tuple[Optional[float], Optional[str]]:
        if self.is_frozen():
            return None, "manual"
        reason = self.should_freeze(
            daily_pnl_pct,
            funding_annualized=funding_annualized,
            notify_fail_streak=notify_fail_streak,
            notify_threshold=notify_threshold,
        )
        if reason:
            self.set_frozen(True)
            return None, reason
        if open_positions >= self.cfg.max_positions:
            return None, "max_positions"

        qty = self.compute_qty(
            nav,
            price,
            stop_px,
            available_quote=available_quote,
            leverage=leverage,
        )
        if qty == 0:
            return None, "zero_qty"
        if symbol_meta is not None and side is not None:
            px, adjusted_qty, error = sanitize_order(
                symbol_meta,
                side,
                price,
                qty,
                auto_bump_min_notional=True,
            )
            if error:
                return None, f"market_{error}"
            qty = adjusted_qty
            lev = self.cfg.leverage if leverage is None else leverage
            if available_quote is not None and lev and lev > 0:
                max_notional = max(0.0, available_quote) * float(lev)
                if px * qty > max_notional + 1e-8:
                    return None, "insufficient_margin"
        elif not self.respects_constraints(qty, price, constraints):
            return None, "market_constraints"
        return qty, None


__all__ = ["MarketConstraints", "RiskGuard"]
