"""Tick touch research log — ย้ายมาจาก backend/db.py เดิม (Phase B move-only)"""

from __future__ import annotations

import json

from backend.db.connection import get_conn

# ─── TICK TOUCH RESEARCH LOG ─────────────────────────────────────────────────


def insert_tick_touch_log(
    signal_time: str,
    symbol: str,
    touch_case: str,
    direction: str,
    entry_price: float,
    ema200_price: float,
    horizon_min: int,
    target_time: str,
    conditions_json: str,
    passed_count: int,
) -> int:
    """บันทึกเหตุการณ์แตะ EMA200 (research — ไม่ส่งสัญญาณจริง ไม่ลง trade_journal)"""
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO tick_touch_log
           (signal_time, symbol, touch_case, direction, entry_price, ema200_price,
            horizon_min, target_time, conditions_json, passed_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal_time,
            symbol,
            touch_case,
            direction,
            entry_price,
            ema200_price,
            horizon_min,
            target_time,
            conditions_json,
            passed_count,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def fetch_last_tick_touch(symbol: str) -> dict | None:
    """แถวล่าสุดของ symbol (ใช้เช็ค cooldown)"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM tick_touch_log WHERE symbol = ? ORDER BY signal_time DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def fetch_pending_tick_touch(symbol: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tick_touch_log WHERE symbol = ? AND result = 'PENDING'",
        (symbol,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_tick_touch_result(log_id: int, exit_price: float, result: str, exit_time: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE tick_touch_log SET result = ?, exit_price = ?, exit_time = ? WHERE id = ?",
        (result, round(exit_price, 5), exit_time, log_id),
    )
    conn.commit()
    conn.close()


def fetch_tick_touch_stats(limit_recent: int = 30) -> dict:
    """สถิติ research: winrate แยกตาม 3 เคส + น้ำหนักโหวตแต่ละ condition
    condition weight = WR เมื่อ cond นั้น pass ในเหตุการณ์แตะ EMA200"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tick_touch_log ORDER BY signal_time DESC").fetchall()
    conn.close()
    rows = [dict(r) for r in rows]

    resolved = [r for r in rows if r["result"] in ("WIN", "LOSE")]

    # ── winrate แยกตาม case ──
    by_case: dict[str, dict] = {}
    for r in resolved:
        c = by_case.setdefault(r["touch_case"], {"n": 0, "wins": 0, "losses": 0, "wr": 0.0})
        c["n"] += 1
        c["wins"] += 1 if r["result"] == "WIN" else 0
    for c in by_case.values():
        c["losses"] = c["n"] - c["wins"]
        c["wr"] = round(100 * c["wins"] / c["n"], 1) if c["n"] else 0.0

    # ── น้ำหนักโหวตแต่ละ condition (เฉพาะ resolved) ──
    by_condition: dict[str, dict] = {}
    for r in resolved:
        try:
            conds = json.loads(r["conditions_json"] or "{}")
        except Exception:
            continue
        for key, val in conds.items():
            if not isinstance(val, dict) or "pass" not in val:
                continue
            d = by_condition.setdefault(
                key, {"true_n": 0, "true_wins": 0, "false_n": 0, "false_wins": 0}
            )
            won = 1 if r["result"] == "WIN" else 0
            if val["pass"]:
                d["true_n"] += 1
                d["true_wins"] += won
            else:
                d["false_n"] += 1
                d["false_wins"] += won
    for d in by_condition.values():
        d["wr_when_true"] = round(100 * d["true_wins"] / d["true_n"], 1) if d["true_n"] else 0.0
        d["wr_when_false"] = round(100 * d["false_wins"] / d["false_n"], 1) if d["false_n"] else 0.0

    total_resolved = len(resolved)
    total_wins = sum(1 for r in resolved if r["result"] == "WIN")

    return {
        "total": len(rows),
        "pending": sum(1 for r in rows if r["result"] == "PENDING"),
        "resolved": total_resolved,
        "wins": total_wins,
        "wr": round(100 * total_wins / total_resolved, 1) if total_resolved else 0.0,
        "by_case": by_case,
        "by_condition": by_condition,
        "recent": [
            {
                k: r[k]
                for k in (
                    "id",
                    "signal_time",
                    "symbol",
                    "touch_case",
                    "direction",
                    "entry_price",
                    "exit_price",
                    "passed_count",
                    "result",
                )
            }
            for r in rows[:limit_recent]
        ],
    }
