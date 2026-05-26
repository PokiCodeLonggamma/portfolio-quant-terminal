"""Couche de persistance SQLite — stocke les snapshots quotidiens pour le calcul de deltas."""

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from config.settings import Config


def _connect() -> sqlite3.Connection:
    Config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Crée les tables si elles n'existent pas."""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS short_interest (
            ticker       TEXT NOT NULL,
            scan_date    TEXT NOT NULL,
            short_float  REAL,
            days_to_cover REAL,
            shares_short INTEGER,
            avg_volume   INTEGER,
            market_cap   REAL,
            price        REAL,
            sector       TEXT,
            PRIMARY KEY (ticker, scan_date)
        );

        CREATE TABLE IF NOT EXISTS institutional (
            ticker       TEXT NOT NULL,
            scan_date    TEXT NOT NULL,
            inst_own_pct REAL,
            inst_trans_pct REAL,
            num_holders  INTEGER,
            PRIMARY KEY (ticker, scan_date)
        );

        CREATE TABLE IF NOT EXISTS options_flow (
            ticker       TEXT NOT NULL,
            scan_date    TEXT NOT NULL,
            put_call_ratio REAL,
            total_call_oi  INTEGER,
            total_put_oi   INTEGER,
            call_oi_change_pct REAL,
            PRIMARY KEY (ticker, scan_date)
        );

        CREATE TABLE IF NOT EXISTS scores (
            ticker       TEXT NOT NULL,
            scan_date    TEXT NOT NULL,
            pillar1      REAL,
            pillar2      REAL,
            pillar3      REAL,
            total_score  REAL,
            signal       TEXT,
            PRIMARY KEY (ticker, scan_date)
        );

        CREATE INDEX IF NOT EXISTS idx_scores_date ON scores(scan_date);
        CREATE INDEX IF NOT EXISTS idx_si_date ON short_interest(scan_date);
    """)
    conn.close()


def upsert_short_interest(ticker: str, data: dict, scan_date: Optional[str] = None) -> None:
    d = scan_date or date.today().isoformat()
    conn = _connect()
    conn.execute("""
        INSERT OR REPLACE INTO short_interest
        (ticker, scan_date, short_float, days_to_cover, shares_short, avg_volume, market_cap, price, sector)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker, d,
        data.get("short_float"),
        data.get("days_to_cover"),
        data.get("shares_short"),
        data.get("avg_volume"),
        data.get("market_cap"),
        data.get("price"),
        data.get("sector"),
    ))
    conn.commit()
    conn.close()


def upsert_institutional(ticker: str, data: dict, scan_date: Optional[str] = None) -> None:
    d = scan_date or date.today().isoformat()
    conn = _connect()
    conn.execute("""
        INSERT OR REPLACE INTO institutional
        (ticker, scan_date, inst_own_pct, inst_trans_pct, num_holders)
        VALUES (?, ?, ?, ?, ?)
    """, (
        ticker, d,
        data.get("inst_own_pct"),
        data.get("inst_trans_pct"),
        data.get("num_holders"),
    ))
    conn.commit()
    conn.close()


def upsert_options(ticker: str, data: dict, scan_date: Optional[str] = None) -> None:
    d = scan_date or date.today().isoformat()
    conn = _connect()
    conn.execute("""
        INSERT OR REPLACE INTO options_flow
        (ticker, scan_date, put_call_ratio, total_call_oi, total_put_oi, call_oi_change_pct)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        ticker, d,
        data.get("put_call_ratio"),
        data.get("total_call_oi"),
        data.get("total_put_oi"),
        data.get("call_oi_change_pct"),
    ))
    conn.commit()
    conn.close()


def upsert_score(ticker: str, data: dict, scan_date: Optional[str] = None) -> None:
    d = scan_date or date.today().isoformat()
    conn = _connect()
    conn.execute("""
        INSERT OR REPLACE INTO scores
        (ticker, scan_date, pillar1, pillar2, pillar3, total_score, signal)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker, d,
        data.get("pillar1"),
        data.get("pillar2"),
        data.get("pillar3"),
        data.get("total_score"),
        data.get("signal"),
    ))
    conn.commit()
    conn.close()


def get_previous_options(ticker: str, scan_date: str) -> Optional[dict]:
    """Retourne le dernier snapshot options AVANT scan_date pour calculer les deltas."""
    conn = _connect()
    row = conn.execute("""
        SELECT * FROM options_flow
        WHERE ticker = ? AND scan_date < ?
        ORDER BY scan_date DESC LIMIT 1
    """, (ticker, scan_date)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_previous_institutional(ticker: str, scan_date: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute("""
        SELECT * FROM institutional
        WHERE ticker = ? AND scan_date < ?
        ORDER BY scan_date DESC LIMIT 1
    """, (ticker, scan_date)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_latest_scores(min_score: float = 0, limit: int = 50) -> list[dict]:
    conn = _connect()
    rows = conn.execute("""
        SELECT s.*, si.short_float, si.days_to_cover, si.market_cap, si.price, si.sector
        FROM scores s
        LEFT JOIN short_interest si ON s.ticker = si.ticker AND s.scan_date = si.scan_date
        WHERE s.scan_date = (SELECT MAX(scan_date) FROM scores)
          AND s.total_score >= ?
        ORDER BY s.total_score DESC
        LIMIT ?
    """, (min_score, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
