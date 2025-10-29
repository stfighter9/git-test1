"""SQLite backed state store for the trading bot."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

DB_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA busy_timeout=5000;",
)

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS candles(
      symbol TEXT,
      tf TEXT,
      ts_close INTEGER,
      o REAL, h REAL, l REAL, c REAL, v REAL,
      PRIMARY KEY(symbol, tf, ts_close)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS orders(
      oid TEXT PRIMARY KEY,
      symbol TEXT,
      side TEXT CHECK(side IN ('buy','sell')),
      qty REAL, px REAL,
      status TEXT,
      ts_created INTEGER, ts_updated INTEGER,
      post_only INTEGER,
      client_order_id TEXT,
      maker INTEGER DEFAULT 1,
      fee REAL DEFAULT 0,
      reject_reason TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_orders_coid ON orders(client_order_id);",
    """
    CREATE TABLE IF NOT EXISTS positions(
      symbol TEXT PRIMARY KEY,
      side TEXT,
      qty REAL,
      entry_px REAL,
      sl_px REAL,
      tp_px REAL,
      leverage REAL,
      ts_open INTEGER,
      tp_order_id TEXT,
      sl_order_id TEXT,
      reduce_only INTEGER DEFAULT 1,
      funding_pnl REAL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ledger(
      ts INTEGER,
      type TEXT,
      amount REAL,
      meta TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_ledger_ts ON ledger(ts);",
    """
    CREATE TABLE IF NOT EXISTS nav_daily(
      ts INTEGER PRIMARY KEY,
      nav REAL,
      trading_pnl REAL,
      fees_pnl REAL,
      funding_pnl REAL
    );
    """,
)


@dataclass
class Candle:
    symbol: str
    tf: str
    ts_close: int
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass
class Order:
    oid: str
    symbol: str
    side: str
    qty: float
    px: float
    status: str
    ts_created: int
    ts_updated: int
    post_only: bool
    client_order_id: str | None = None
    maker: bool = True
    fee: float = 0.0
    reject_reason: str | None = None


@dataclass
class Position:
    symbol: str
    side: str
    qty: float
    entry_px: float
    sl_px: float
    tp_px: float
    leverage: float
    ts_open: int
    tp_order_id: str | None = None
    sl_order_id: str | None = None
    reduce_only: bool = True
    funding_pnl: float = 0.0


@dataclass
class LedgerEntry:
    ts: int
    type: str
    amount: float
    meta: Optional[str] = None


@dataclass
class DailyNav:
    ts: int
    nav: float
    trading_pnl: float
    fees_pnl: float
    funding_pnl: float


class StateStore:
    """Context manager providing SQLite helpers."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def _commit(self) -> None:
        if self._conn:
            self._conn.commit()

    def __enter__(self) -> "StateStore":
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        for pragma in DB_PRAGMAS:
            self._conn.execute(pragma)
        for stmt in SCHEMA_STATEMENTS:
            self._conn.executescript(stmt)
        self._conn.commit()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._conn:
            return
        if exc:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()
        self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if not self._conn:
            raise RuntimeError("StateStore must be used as a context manager")
        return self._conn

    # Candle helpers
    def upsert_candles(self, rows: Iterable[Candle]) -> None:
        sql = (
            "INSERT INTO candles(symbol, tf, ts_close, o, h, l, c, v) "
            "VALUES (:symbol, :tf, :ts_close, :o, :h, :l, :c, :v) "
            "ON CONFLICT(symbol, tf, ts_close) DO UPDATE SET "
            "o=excluded.o, h=excluded.h, l=excluded.l, c=excluded.c, v=excluded.v"
        )
        self.conn.executemany(sql, [c.__dict__ for c in rows])
        self._commit()

    def get_last_n_candles(self, symbol: str, tf: str, n: int) -> List[Candle]:
        cur = self.conn.execute(
            "SELECT * FROM candles WHERE symbol=? AND tf=? ORDER BY ts_close DESC LIMIT ?",
            (symbol, tf, n),
        )
        return [Candle(**dict(row)) for row in reversed(cur.fetchall())]

    # Order helpers
    def upsert_order(self, order: Order) -> None:
        sql = (
            "INSERT INTO orders(oid, symbol, side, qty, px, status, ts_created, ts_updated, post_only, "
            "client_order_id, maker, fee, reject_reason) "
            "VALUES (:oid, :symbol, :side, :qty, :px, :status, :ts_created, :ts_updated, :post_only, "
            ":client_order_id, :maker, :fee, :reject_reason) "
            "ON CONFLICT(oid) DO UPDATE SET "
            "symbol=excluded.symbol, side=excluded.side, qty=excluded.qty, px=excluded.px, "
            "status=excluded.status, ts_updated=excluded.ts_updated, "
            "post_only=excluded.post_only, client_order_id=excluded.client_order_id, "
            "maker=excluded.maker, fee=excluded.fee, reject_reason=excluded.reject_reason"
        )
        payload = order.__dict__.copy()
        payload["post_only"] = int(order.post_only)
        payload["maker"] = int(order.maker)
        self.conn.execute(sql, payload)
        self._commit()

    def get_order(self, oid: str) -> Optional[Order]:
        cur = self.conn.execute("SELECT * FROM orders WHERE oid=?", (oid,))
        row = cur.fetchone()
        if row is None:
            return None
        data = dict(row)
        data["post_only"] = bool(data["post_only"])
        data["maker"] = bool(data["maker"])
        return Order(**data)

    def list_orders(
        self,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Order]:
        query = "SELECT * FROM orders"
        conditions: list[str] = []
        params: list[object] = []
        if symbol:
            conditions.append("symbol=?")
            params.append(symbol)
        if status:
            conditions.append("status=?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        cur = self.conn.execute(query, params)
        rows = []
        for row in cur.fetchall():
            data = dict(row)
            data["post_only"] = bool(data["post_only"])
            data["maker"] = bool(data["maker"])
            rows.append(Order(**data))
        return rows

    def get_order_by_coid(self, client_order_id: str) -> Optional[Order]:
        cur = self.conn.execute(
            "SELECT * FROM orders WHERE client_order_id=?", (client_order_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        data = dict(row)
        data["post_only"] = bool(data["post_only"])
        data["maker"] = bool(data["maker"])
        return Order(**data)

    def delete_order(self, oid: str) -> None:
        self.conn.execute("DELETE FROM orders WHERE oid=?", (oid,))
        self._commit()

    def update_order_status(self, oid: str, status: str, ts_updated: int) -> None:
        self.conn.execute(
            "UPDATE orders SET status=?, ts_updated=? WHERE oid=?",
            (status, ts_updated, oid),
        )
        self._commit()

    # Position helpers
    def set_position(self, position: Position) -> None:
        sql = (
            "INSERT INTO positions(symbol, side, qty, entry_px, sl_px, tp_px, leverage, ts_open, "
            "tp_order_id, sl_order_id, reduce_only, funding_pnl) "
            "VALUES (:symbol, :side, :qty, :entry_px, :sl_px, :tp_px, :leverage, :ts_open, :tp_order_id, :sl_order_id, :reduce_only, :funding_pnl) "
            "ON CONFLICT(symbol) DO UPDATE SET "
            "side=excluded.side, qty=excluded.qty, entry_px=excluded.entry_px, sl_px=excluded.sl_px, "
            "tp_px=excluded.tp_px, leverage=excluded.leverage, ts_open=excluded.ts_open, "
            "tp_order_id=excluded.tp_order_id, sl_order_id=excluded.sl_order_id, "
            "reduce_only=excluded.reduce_only, funding_pnl=excluded.funding_pnl"
        )
        payload = position.__dict__.copy()
        payload["reduce_only"] = int(position.reduce_only)
        self.conn.execute(sql, payload)
        self._commit()

    def get_position(self, symbol: str) -> Optional[Position]:
        cur = self.conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,))
        row = cur.fetchone()
        if row is None:
            return None
        data = dict(row)
        data["reduce_only"] = bool(data["reduce_only"])
        return Position(**data)

    def clear_position(self, symbol: str) -> None:
        self.conn.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
        self._commit()

    # Ledger helpers
    def insert_ledger_entry(self, entry: LedgerEntry) -> None:
        sql = "INSERT INTO ledger(ts, type, amount, meta) VALUES (:ts, :type, :amount, :meta)"
        self.conn.execute(sql, entry.__dict__)
        self._commit()

    def list_ledger_entries(self, limit: Optional[int] = None) -> List[LedgerEntry]:
        if limit:
            cur = self.conn.execute("SELECT * FROM ledger ORDER BY ts DESC LIMIT ?", (limit,))
        else:
            cur = self.conn.execute("SELECT * FROM ledger ORDER BY ts DESC")
        return [LedgerEntry(**dict(row)) for row in cur.fetchall()]

    # Daily NAV helpers
    def upsert_daily_nav(self, nav: DailyNav) -> None:
        sql = (
            "INSERT INTO nav_daily(ts, nav, trading_pnl, fees_pnl, funding_pnl) "
            "VALUES (:ts, :nav, :trading_pnl, :fees_pnl, :funding_pnl) "
            "ON CONFLICT(ts) DO UPDATE SET "
            "nav=excluded.nav, trading_pnl=excluded.trading_pnl, fees_pnl=excluded.fees_pnl, "
            "funding_pnl=excluded.funding_pnl"
        )
        self.conn.execute(sql, nav.__dict__)
        self._commit()

    def get_daily_nav(self, ts: int) -> Optional[DailyNav]:
        cur = self.conn.execute("SELECT * FROM nav_daily WHERE ts=?", (ts,))
        row = cur.fetchone()
        return DailyNav(**dict(row)) if row else None


__all__ = [
    "Candle",
    "DailyNav",
    "LedgerEntry",
    "Order",
    "Position",
    "StateStore",
]
