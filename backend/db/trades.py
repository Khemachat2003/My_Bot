"""db.trades — trade journal (P&L จำลอง) — ย้ายจาก db.py แบบ move-only"""

from __future__ import annotations

from backend.db.connection import get_conn
from backend.db.stats import wilson_ci

# ─── TRADE JOURNAL ───────────────────────────────────────────────────────────


def insert_trade(
    signal_id: int,
    signal_type: str,
    timeframe: str,
    symbol: str,
    direction: str,
    entry_price: float,
    entry_time: str,
    hold_min: int,
    confidence: float | None = None,
    model_version: str | None = None,
    payout: float = 0.82,
) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO trade_journal
           (signal_id, signal_type, timeframe, symbol, direction, entry_price,
            entry_time, hold_min, confidence, model_version, payout, result)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')""",
        (
            signal_id,
            signal_type,
            timeframe,
            symbol,
            direction,
            entry_price,
            entry_time,
            hold_min,
            confidence,
            model_version,
            payout,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_trade_result(trade_id: int, exit_price: float, exit_time: str, result: str) -> None:
    """บันทึกผล WIN/LOSE + pnl จำลอง (win = +1 unit, lose = -1 unit ของ payout)"""
    conn = get_conn()
    row = conn.execute(
        "SELECT direction, payout FROM trade_journal WHERE id = ?", (trade_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return
    pnl = row["payout"] if result == "WIN" else (-1.0 if result == "LOSE" else 0.0)
    conn.execute(
        """UPDATE trade_journal SET exit_price = ?, exit_time = ?, result = ?,
           pnl = ?, win_amount = CASE WHEN ? = 'WIN' THEN ? ELSE 0 END,
           loss_amount = CASE WHEN ? = 'LOSE' THEN 1 ELSE 0 END
           WHERE id = ?""",
        (exit_price, exit_time, result, pnl, result, row["payout"], result, trade_id),
    )
    conn.commit()
    conn.close()


def fetch_recent_trades(limit: int = 100, signal_type: str | None = None) -> list[dict]:
    conn = get_conn()
    sql = "SELECT * FROM trade_journal"
    params: list = []
    if signal_type:
        sql += " WHERE signal_type = ?"
        params.append(signal_type)
    sql += " ORDER BY entry_time DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_journal_stats(payout: float = 0.82) -> dict:
    """P&L รวม / winrate / equity curve จำลอง จาก trade_journal ทั้งหมด"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trade_journal WHERE result IN ('WIN', 'LOSE') AND COALESCE(phantom, 0) = 0 "
        "ORDER BY exit_time"
    ).fetchall()
    conn.close()
    rows = [dict(r) for r in rows]

    n = len(rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    total_pnl = sum(r["pnl"] or 0 for r in rows)
    winrate = round(100 * wins / n, 2) if n else 0.0
    ci_low, ci_high = wilson_ci(wins, n)
    breakeven = round(1 / (1 + payout) * 100, 2)

    # equity curve (cumulative pnl)
    equity = []
    cum = 0.0
    for r in rows:
        cum += r["pnl"] or 0
        equity.append({"t": r["exit_time"], "equity": round(cum, 4)})

    # daily breakdown
    daily: dict[str, dict] = {}
    for r in rows:
        day = (r["exit_time"] or r["entry_time"])[:10]
        d = daily.setdefault(day, {"day": day, "n": 0, "wins": 0, "pnl": 0.0})
        d["n"] += 1
        d["wins"] += 1 if r["result"] == "WIN" else 0
        d["pnl"] += r["pnl"] or 0

    daily_list = sorted(daily.values(), key=lambda x: x["day"], reverse=True)
    for d in daily_list:
        d["winrate"] = round(100 * d["wins"] / d["n"], 2) if d["n"] else 0.0
        d["pnl"] = round(d["pnl"], 4)

    return {
        "n": n,
        "wins": wins,
        "losses": n - wins,
        "winrate": winrate,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "breakeven": breakeven,
        "total_pnl": round(total_pnl, 4),
        "equity": equity[-200:],
        "daily": daily_list[:30],
    }
