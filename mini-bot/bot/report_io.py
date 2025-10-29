"""Helpers for writing structured CSV outputs."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable

TRADE_FIELDS = [
    "trade_id",
    "fold",
    "symbol",
    "side",
    "entry_time",
    "exit_time",
    "entry_px",
    "exit_px",
    "qty",
    "sl_px",
    "tp_px",
    "bars_held",
    "gross_pnl",
    "fees",
    "funding",
    "net_pnl",
    "maker_ratio",
    "reason_exit",
    "p_buy",
    "p_sell",
    "tau",
    "k_tp",
    "k_sl",
    "H",
    "regime_tag",
]


class CsvWriter:
    def __init__(self, path: str | Path, header: Iterable[str]):
        self.path = Path(path)
        self.header = list(header)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", newline="", encoding="utf8") as handle:
                writer = csv.DictWriter(handle, fieldnames=self.header)
                writer.writeheader()

    def append(self, row: Dict[str, object]) -> None:
        with self.path.open("a", newline="", encoding="utf8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.header)
            writer.writerow(row)


def append_trade_csv(path: str | Path, row: Dict[str, object]) -> None:
    CsvWriter(path, TRADE_FIELDS).append(row)


__all__ = ["append_trade_csv", "CsvWriter", "TRADE_FIELDS"]
