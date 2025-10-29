"""Toy execution simulator for post-only ladders."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


@dataclass
class VenueMeta:
    maker_fee: float = 0.0002
    taker_fee: float = 0.0007


@dataclass
class LadderOrder:
    price: float
    qty: float
    level: int


@dataclass
class Fill:
    order: LadderOrder
    filled_qty: float
    filled_price: float
    maker: bool
    time_to_fill_min: float


@dataclass
class Reject:
    order: LadderOrder
    reason: str


class ExecSim:
    def __init__(self, venue_meta: VenueMeta, spread_stats: float, depth_stats: float) -> None:
        self.venue_meta = venue_meta
        self.spread_stats = spread_stats
        self.depth_stats = depth_stats

    def submit_ladder(
        self,
        ladder: Sequence[LadderOrder],
        timeout_bars: int,
        bar_duration_h: float,
    ) -> List[Fill | Reject]:
        results: List[Fill | Reject] = []
        for order in ladder:
            if order.price <= 0 or order.qty <= 0:
                results.append(Reject(order=order, reason="invalid"))
                continue
            # crude fill logic using depth stats: if qty below threshold treat as filled
            if order.qty <= self.depth_stats:
                ttf = min(timeout_bars * bar_duration_h * 60, 5.0)
                results.append(
                    Fill(
                        order=order,
                        filled_qty=order.qty,
                        filled_price=order.price - self.spread_stats,
                        maker=True,
                        time_to_fill_min=ttf,
                    )
                )
            else:
                results.append(Reject(order=order, reason="timeout"))
        return results


__all__ = ["ExecSim", "VenueMeta", "LadderOrder", "Fill", "Reject"]
