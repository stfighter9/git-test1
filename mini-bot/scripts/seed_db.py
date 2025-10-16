#!/usr/bin/env python3
"""Initialize the SQLite database schema."""
from pathlib import Path

from bot.state_store import StateStore


def main() -> None:
    db_path = Path("data/mini.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with StateStore(db_path):
        pass
    print(f"Initialized database at {db_path}")


if __name__ == "__main__":
    main()
