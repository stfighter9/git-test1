"""Aggregate metrics across folds."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable


def _load_metrics(path: Path) -> Dict[str, float]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def aggregate_metrics(folds_dir: str | Path) -> Dict[str, float]:
    folds_path = Path(folds_dir)
    metrics: Dict[str, Iterable[float]] = {}
    for metrics_path in folds_path.glob("fold_*/metrics.json"):
        data = _load_metrics(metrics_path)
        for key, value in data.items():
            metrics.setdefault(key, []).append(value)
    aggregated: Dict[str, float] = {}
    for key, values in metrics.items():
        aggregated[key] = float(mean(values))
    return aggregated


__all__ = ["aggregate_metrics"]
