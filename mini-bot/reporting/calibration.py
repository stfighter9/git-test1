"""Calibration helpers."""
from __future__ import annotations

import math
from typing import Iterable, List, Tuple


def reliability_table(probs: Iterable[float], y: Iterable[int], n_bins: int = 10):
    probs_list = list(probs)
    y_list = list(y)
    bins: List[Tuple[float, float, int, float, float]] = []
    if not probs_list:
        return []
    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    for i in range(n_bins):
        left, right = bin_edges[i], bin_edges[i + 1]
        members = [
            (p, t)
            for p, t in zip(probs_list, y_list)
            if left <= p < (right if i < n_bins - 1 else right + 1e-9)
        ]
        if not members:
            bins.append((0.0, 0.0, 0, left, right))
        else:
            mean_prob = sum(p for p, _ in members) / len(members)
            emp_prob = sum(t for _, t in members) / len(members)
            bins.append((emp_prob, mean_prob, len(members), left, right))
    return bins


def brier_score(probs: Iterable[float], y: Iterable[int]) -> float:
    total = 0.0
    count = 0
    for p, target in zip(probs, y):
        total += (p - target) ** 2
        count += 1
    return total / count if count else math.nan


__all__ = ["reliability_table", "brier_score"]
