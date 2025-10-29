"""Plot helpers (matplotlib optional)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

try:  # pragma: no cover - optional dependency
    import matplotlib.pyplot as plt  # type: ignore
except Exception:  # pragma: no cover
    plt = None


def _maybe_plot(path: Path) -> None:
    if plt is None:  # pragma: no cover - no plotting backend in tests
        path.write_text("plotting-disabled")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path)
    plt.close()


def plot_equity_oos(exp_id: str, equity: Iterable[float] | None = None) -> Path:
    path = Path("experiments") / exp_id / "aggregate" / "equity_oos.png"
    if plt and equity is not None:
        plt.figure()
        plt.plot(list(equity))
        plt.title("Equity OOS")
    _maybe_plot(path)
    return path


def plot_reliability(exp_id: str, points: Iterable[tuple[float, float]] | None = None) -> Path:
    path = Path("experiments") / exp_id / "aggregate" / "reliability.png"
    if plt and points is not None:
        xs, ys = zip(*points)
        plt.figure()
        plt.plot(xs, ys)
        plt.title("Reliability")
    _maybe_plot(path)
    return path


def plot_exec(exp_id: str, fills: Iterable[float] | None = None) -> Path:
    path = Path("experiments") / exp_id / "aggregate" / "exec.png"
    if plt and fills is not None:
        plt.figure()
        plt.hist(list(fills), bins=10)
        plt.title("Execution")
    _maybe_plot(path)
    return path


def plot_funding_decomp(exp_id: str, funding: Iterable[float] | None = None) -> Path:
    path = Path("experiments") / exp_id / "aggregate" / "funding.png"
    if plt and funding is not None:
        plt.figure()
        plt.bar(range(len(list(funding))), list(funding))
        plt.title("Funding")
    _maybe_plot(path)
    return path


__all__ = [
    "plot_equity_oos",
    "plot_reliability",
    "plot_exec",
    "plot_funding_decomp",
]
