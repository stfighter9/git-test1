"""Recommendation helper."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def recommend_params(exp_id: str) -> Dict[str, object]:
    metrics_path = Path("experiments") / exp_id / "aggregate" / "metrics_oos.json"
    if not metrics_path.exists():
        return {}
    metrics = json.loads(metrics_path.read_text())
    recommendation = {
        "tau": metrics.get("tau", 0.65),
        "k_tp": metrics.get("k_tp", 2.0),
        "k_sl": metrics.get("k_sl", 1.0),
        "H": metrics.get("H", "4h"),
        "regime": metrics.get("regime", {}),
    }
    recommendations_path = metrics_path.parent / "recommendations.yaml"
    content = "\n".join(f"{k}: {v}" for k, v in recommendation.items())
    recommendations_path.write_text(content)
    return recommendation


__all__ = ["recommend_params"]
