"""db.signals_setup — สัญญาณ Rule-Based (🔵 System 1) — ย้ายจาก db.py แบบ move-only

ห้าม insert/update ข้าม schema — ฝั่ง Rule-Based แตะเฉพาะ setup_* functions
เพื่อรักษา Decoupled Architecture ตาม spec (ดู docstring เดิมของ db.py)
"""

from __future__ import annotations

from backend.db.connection import get_conn
from backend.db.stats import _compute_stats, _compute_stats_by_timeframe


# RULE-BASED SETUP SIGNALS
def insert_setup_signal(
    signal_time: str,
    entry_price: float,
    direction: str,
    confidence: float,
    horizon_min: int,
    target_time: str,
    timeframe: str = "M1",
    score: float | None = None,
    total: int | None = None,
    tier: str = "NONE",
    symbol: str = "frxXAUUSD",
    ema200_price: float | None = None,
    dist200_pct: float | None = None,
    near_ema200: bool | None = None,
    crossed_ema100: bool | None = None,
    gold_slope_1h: float | None = None,
    dxy_slope_24: float | None = None,
    dxy_rsi: float | None = None,
    gate_agree: bool | None = None,
    importance: int | None = None,
    conditions_passed: int | None = None,
    conditions_log_json: str | None = None,
) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO setup_signals
           (signal_time, timeframe, entry_price, direction, confidence,
            score, total, tier, horizon_min, target_time, result, symbol,
            ema200_price, dist200_pct, near_ema200, crossed_ema100,
            gold_slope_1h, dxy_slope_24, dxy_rsi, gate_agree,
            importance, conditions_passed, conditions_log_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?,
                   ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal_time,
            timeframe,
            entry_price,
            direction,
            confidence,
            score,
            total,
            tier,
            horizon_min,
            target_time,
            symbol,
            ema200_price,
            dist200_pct,
            (1 if near_ema200 else 0) if near_ema200 is not None else None,
            (1 if crossed_ema100 else 0) if crossed_ema100 is not None else None,
            gold_slope_1h,
            dxy_slope_24,
            dxy_rsi,
            (1 if gate_agree else 0) if gate_agree is not None else None,
            importance,
            conditions_passed,
            conditions_log_json,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_setup_signal_result(signal_id: int, exit_price: float, result: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE setup_signals SET exit_price = ?, result = ? WHERE id = ?",
        (exit_price, result, signal_id),
    )
    conn.commit()
    conn.close()


def fetch_pending_setup_signals(symbol: str | None = None) -> list[dict]:
    conn = get_conn()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM setup_signals WHERE result = 'PENDING' AND symbol = ?",
            (symbol,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM setup_signals WHERE result = 'PENDING'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_recent_setup_signals(
    limit: int = 100, symbol: str | None = None, exclude_tick: bool = False
) -> list[dict]:
    conn = get_conn()
    where_parts = []
    params = []
    if symbol:
        where_parts.append("symbol = ?")
        params.append(symbol)
    if exclude_tick:
        where_parts.append("timeframe != 'TICK'")
    where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM setup_signals{where} ORDER BY signal_time DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_last_setup_signal(timeframe: str, symbol: str | None = None) -> dict | None:
    """สัญญาณล่าสุดของ TF นี้ (สำหรับ cooldown — กันยิงซ้ำหลัง restart)"""
    conn = get_conn()
    if symbol:
        row = conn.execute(
            "SELECT * FROM setup_signals WHERE timeframe = ? AND symbol = ? "
            "ORDER BY signal_time DESC LIMIT 1",
            (timeframe, symbol),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM setup_signals WHERE timeframe = ? ORDER BY signal_time DESC LIMIT 1",
            (timeframe,),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def count_setup_signals_since(start_iso: str, symbol: str | None = None) -> int:
    """จำนวนสัญญาณที่ยิงตั้งแต่เวลา start_iso (ใช้สำหรับ daily cap)"""
    conn = get_conn()
    if start_iso:
        if symbol:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM setup_signals WHERE signal_time >= ? AND symbol = ?",
                (start_iso, symbol),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM setup_signals WHERE signal_time >= ?",
                (start_iso,),
            ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) AS c FROM setup_signals").fetchone()
    conn.close()
    return int(row["c"])


def compute_setup_stats(payout: float = 0.82) -> dict:
    return _compute_stats("setup_signals", payout)


def compute_setup_stats_by_timeframe(payout: float = 0.82) -> dict:
    return _compute_stats_by_timeframe("setup_signals", payout)
