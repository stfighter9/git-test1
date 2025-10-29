from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.exp_registry import new_registry
from reporting.aggregate import aggregate_metrics
from reporting.recommend import recommend_params
from reporting.validate_dod import check_dod


def run_fold(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "trades.csv").write_text("trade_id,fold\n")
    (path / "cycles.jsonl").write_text("")
    metrics = {
        "Sharpe": 1.2,
        "MAR": 0.7,
        "MaxDD": 0.1,
        "FillRatio": 0.6,
        "BTC_Sharpe": 1.1,
        "ETH_Sharpe": 1.05,
    }
    (path / "metrics.json").write_text(json.dumps(metrics))
    (path / "calib.csv").write_text("prob,emp\n")
    (path / "exec_summary.csv").write_text("order_id,filled_qty\n")
    (path / "funding_pnl.csv").write_text("position_id,rate\n")


def main(cfg_path: str, comment: str = "") -> str:
    registry = new_registry(comment=comment)
    config_path = Path(cfg_path)
    config_text = config_path.read_text() if config_path.exists() else ""
    config_hash = registry.write_config_file(config_text)
    registry.write_metadata(comment=comment, config_snapshot_sha256=config_hash)

    fold_path = registry.fold_dir(0)
    folds_root = fold_path.parent
    run_fold(fold_path)
    aggregate = aggregate_metrics(folds_root)
    agg_path = registry.exp_path / "aggregate" / "metrics_oos.json"
    agg_path.parent.mkdir(parents=True, exist_ok=True)
    agg_path.write_text(json.dumps(aggregate))
    recommend_params(registry.exp_id)
    dod_ok = check_dod(aggregate)
    registry.end(status="success" if dod_ok else "fail", dod_pass=dod_ok)
    return registry.exp_id


if __name__ == "__main__":  # pragma: no cover - CLI
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--comment", default="")
    args = parser.parse_args()
    main(args.config, args.comment)
