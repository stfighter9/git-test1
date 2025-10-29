"""Lightweight JSON line logger."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def jlog(path: str | Path, evt: str, **payload: Any) -> None:
    record = {"evt": evt, **payload}
    line = json.dumps(record, sort_keys=True)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8") as handle:
        handle.write(line + "\n")


__all__ = ["jlog"]
