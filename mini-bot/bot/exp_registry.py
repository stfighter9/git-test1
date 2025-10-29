"""Experiment registry helpers with reproducibility metadata."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    """Compute a SHA-256 hex digest for *data*."""
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def _git_commit_short() -> str:
    """Return the short git commit hash if available."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception:  # pragma: no cover - fall back when git missing
        return "nogit"


def _ccxt_version() -> Optional[str]:
    try:  # pragma: no cover - optional dependency in tests
        import ccxt  # type: ignore

        return getattr(ccxt, "__version__", None) or "unknown"
    except Exception:
        return None


@dataclass
class ExpRegistry:
    """Track experiment artefacts and metadata for reproducibility."""

    root: Path
    exp_path: Path
    exp_id: str
    seed: int
    git_commit: str

    def ensure_dirs(self) -> None:
        """Create the standard folder structure for the experiment."""
        (self.exp_path / "folds").mkdir(parents=True, exist_ok=True)
        (self.exp_path / "aggregate" / "plots").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------
    @property
    def registry_path(self) -> Path:
        return self.exp_path / "registry.json"

    def _base_metadata(self) -> dict[str, Any]:
        return {
            "exp_id": self.exp_id,
            "created_at": _utc_now_iso(),
            "seed": self.seed,
            "git_commit": self.git_commit,
            "python": sys.version.split()[0],
            "ccxt": _ccxt_version(),
            "platform": platform.platform(),
            "timezone": list(time.tzname),
            "status": "running",
        }

    def write_metadata(
        self,
        *,
        comment: Optional[str] = None,
        config_snapshot_sha256: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        """Persist registry metadata, merging with existing payload."""

        path = self.registry_path
        if path.exists():
            payload: dict[str, Any] = json.loads(path.read_text())
        else:
            payload = self._base_metadata()
        if comment is not None:
            payload["comment"] = comment
        if config_snapshot_sha256 is not None:
            payload["config_snapshot_sha256"] = config_snapshot_sha256
        if extra:
            payload.setdefault("extra", {}).update(extra)
        path.write_text(json.dumps(payload, indent=2))

    def write_config_file(self, cfg_text: str, filename: str = "config.yaml") -> str:
        """Write the configuration snapshot and return its SHA-256 hash."""

        path = self.exp_path / filename
        path.write_text(cfg_text)
        return _sha256_bytes(cfg_text.encode())

    def fold_dir(self, index: int) -> Path:
        """Return the fold directory for *index*, creating it if needed."""

        fold_path = self.exp_path / "folds" / f"fold_{index:02d}"
        fold_path.mkdir(parents=True, exist_ok=True)
        return fold_path

    def end(self, status: str, dod_pass: Optional[bool] = None) -> None:
        """Mark the experiment as finished and record DoD status."""

        payload = json.loads(self.registry_path.read_text()) if self.registry_path.exists() else {}
        payload.update(
            {
                "ended_at": _utc_now_iso(),
                "status": status,
                "dod_pass": bool(dod_pass) if dod_pass is not None else None,
            }
        )
        self.registry_path.write_text(json.dumps(payload, indent=2))


def new_registry(
    root: str | Path = "experiments",
    comment: str = "",
    seed: Optional[int] = None,
) -> ExpRegistry:
    """Create a new experiment registry in *root* and return it."""

    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    pid_suffix = os.getpid() % 10000
    base_id = f"EXP_{ts}_{pid_suffix:04d}"
    exp_path = root_path / base_id
    counter = 0
    while exp_path.exists():
        counter += 1
        exp_path = root_path / f"{base_id}_{counter:02d}"

    exp_path.mkdir(parents=False, exist_ok=False)

    registry = ExpRegistry(
        root=root_path,
        exp_path=exp_path,
        exp_id=exp_path.name,
        seed=seed if seed is not None else int.from_bytes(os.urandom(4), "big"),
        git_commit=_git_commit_short(),
    )
    registry.ensure_dirs()
    registry.write_metadata(comment=comment, config_snapshot_sha256="")
    return registry


__all__ = ["ExpRegistry", "new_registry"]
