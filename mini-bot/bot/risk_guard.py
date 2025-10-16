"""Risk management helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from bot.config import TradingConfig


@dataclass
class MarketConstraints:
    min_qty: float
    min_notional: float


class RiskGuard:
    def __init__(self, cfg: TradingConfig, freeze_path: Path | str = Path("data/freeze.flag")) -> None:
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
        return abs(price - stop_px) / price if price > 0 else 0.0

    def position_size(self, nav: float, price: float, stop_px: float) -> float:
        stop_pct = self.compute_stop_pct(price, stop_px)
        if stop_pct <= 0:
            return 0.0
        qty = nav * self.cfg.risk_pct / (stop_pct * price)
        return max(qty, 0.0)

    # Daily loss limit --------------------------------------------------
    def check_daily_loss_limit(self, daily_pnl_pct: float) -> bool:
        if daily_pnl_pct <= -self.cfg.daily_loss_limit_pct:
            self.set_frozen(True)
            return False
        return True

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
    ) -> Optional[float]:
        if self.is_frozen():
            return None
        if not self.check_daily_loss_limit(daily_pnl_pct):
            return None
        qty = self.position_size(nav, price, stop_px)
        if qty == 0:
            return None
        if not self.respects_constraints(qty, price, constraints):
            return None
        return qty


__all__ = ["MarketConstraints", "RiskGuard"]
