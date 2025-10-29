import json
from pathlib import Path

from scripts.exp_wfo import main as run_wfo


def test_wfo_smoke(tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("wfo: {}\n")
    exp_id = run_wfo(str(cfg_path), comment="test")
    exp_dir = Path("experiments") / exp_id
    assert (exp_dir / "folds" / "fold_00" / "metrics.json").exists()
    assert (exp_dir / "aggregate" / "metrics_oos.json").exists()
    assert (exp_dir / "aggregate" / "recommendations.yaml").exists()
    registry = json.loads((exp_dir / "registry.json").read_text())
    assert registry["comment"] == "test"
    assert registry["status"] in {"success", "fail"}
    assert "config_snapshot_sha256" in registry and len(registry["config_snapshot_sha256"]) == 64
