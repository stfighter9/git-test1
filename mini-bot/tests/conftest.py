import sqlite3
from pathlib import Path

import pytest

from bot.state_store import StateStore


@pytest.fixture()
def temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    with StateStore(db_path) as store:
        pass
    return db_path
