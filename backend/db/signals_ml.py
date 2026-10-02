"""db.signals_ml — สัญญาณ ML (🟢 System 2) + ml_latest — ย้ายจาก db.py แบบ move-only

ห้าม insert/update ข้าม schema — ฝั่ง ML แตะเฉพาะ ml_* functions
"""

from __future__ import annotations

import json

from backend.db.connection import get_conn
from backend.db.stats import _compute_stats, _compute_stats_by_timeframe


# ML MODEL SIGNALS
def insert_ml_signal(
    signal_time: str,
    entry_price: float,
    direction: str,
    confidence: float,
    horizon_min: int,
    target_time: str,
    timeframe: str = "M1",
    prob_up: float | None = None,
    prob_down: float | None = None,
    threshold_used: float | None = None,
    model_version: str | None = None,
    features: dict | None = None,
) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO ml_signals
           (signal_time, timeframe, entry_price, direction, confidence,
            prob_up, prob_down, threshold_used, model_version,
            horizon_min, target_time, result, features_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
        (
            signal_time,
            timeframe,
            entry_price,
            direction,
            confidence,
            prob_up,
            prob_down,
            threshold_used,
            model_version,
            horizon_min,
            target_time,
            json.dumps(features) if features is not None else None,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_ml_signal_result(signal_id: int, exit_price: float, result: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE ml_signals SET exit_price = ?, result = ? WHERE id = ?",
        (exit_price, result, signal_id),
    )
    conn.commit()
    conn.close()


def fetch_pending_ml_signals() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM ml_signals WHERE result = 'PENDING'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_recent_ml_signals(limit: int = 100) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ml_signals ORDER BY signal_time DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_ml_signals_since(start_iso: str) -> int:
    """จำนวน ML signals ที่ยิงตั้งแต่ start_iso (ใช้ daily cap 20 ไม้)"""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM ml_signals WHERE signal_time >= ?",
        (start_iso,),
    ).fetchone()
    conn.close()
    return int(row["c"]) if row else 0


def compute_ml_stats(payout: float = 0.82) -> dict:
    return _compute_stats("ml_signals", payout)


def compute_ml_stats_by_timeframe(payout: float = 0.82) -> dict:
    return _compute_stats_by_timeframe("ml_signals", payout)


def upsert_ml_latest(
    timeframe: str,
    ts: str,
    prob_up: float,
    prob_down: float,
    signal: str,
    confidence: float,
    threshold_used: float,
) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO ml_latest (timeframe, ts, prob_up, prob_down, signal, confidence, threshold_used)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(timeframe) DO UPDATE SET
             ts=excluded.ts, prob_up=excluded.prob_up, prob_down=excluded.prob_down,
             signal=excluded.signal, confidence=excluded.confidence,
             threshold_used=excluded.threshold_used""",
        (timeframe, ts, prob_up, prob_down, signal, confidence, threshold_used),
    )
    conn.commit()
    conn.close()


def fetch_ml_latest() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM ml_latest").fetchall()
    conn.close()
    return {r["timeframe"]: dict(r) for r in rows}
