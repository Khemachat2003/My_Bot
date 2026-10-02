"""CFD paper trading — ย้ายมาจาก backend/db.py เดิม (Phase B move-only)"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from backend.db.connection import get_conn

# ─── CFD PAPER TRADING ───────────────────────────────────────────────────────

CFD_SL_PIPS = 20
CFD_TP1_PIPS = 40
CFD_TP2_PIPS = 60
CFD_SPREAD_PIPS = 1.5
CFD_CAPITAL = 5000.0
CFD_RISK_PCT = 0.01

# ── pip_size per symbol ──
_SYMBOL_PIP = {
    "XAUUSD": 1.0,
    "frxXAUUSD": 1.0,
    "USDJPY": 0.01,
    "frxUSDJPY": 0.01,
    "EURJPY": 0.01,
    "frxEURJPY": 0.01,
    "GBPJPY": 0.01,
    "frxGBPJPY": 0.01,
    "AUDJPY": 0.01,
    "frxAUDJPY": 0.01,
    "EURUSD": 0.0001,
    "frxEURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "frxGBPUSD": 0.0001,
    "AUDUSD": 0.0001,
    "frxAUDUSD": 0.0001,
    "NZDUSD": 0.0001,
    "frxNZDUSD": 0.0001,
    "USDCAD": 0.0001,
    "frxUSDCAD": 0.0001,
    "USDCHF": 0.0001,
    "frxUSDCHF": 0.0001,
}
_DEFAULT_PIP = 0.0001


def get_pip_size(symbol: str) -> float:
    return _SYMBOL_PIP.get(symbol, _DEFAULT_PIP)


def get_pip_value(symbol: str) -> float:
    """pip_value = profit per 1 pip for 1 lot (standard)"""
    ps = get_pip_size(symbol)
    if ps >= 1.0:
        return 100.0
    return 10.0


def _cfd_lot_size(symbol: str = "frxXAUUSD") -> float:
    risk = CFD_CAPITAL * CFD_RISK_PCT
    pv = get_pip_value(symbol)
    return round(risk / (CFD_SL_PIPS * pv), 3)


def insert_cfd_paper_trade(
    signal_id: int,
    signal_type: str,
    symbol: str,
    direction: str,
    entry_price: float,
    entry_time: str,
) -> int | None:
    """สร้าง CFD paper trade เมื่อ signal ใหม่ถูกสร้าง
    จำกัดสูงสุด 10 OPEN trades ต่อ symbol"""
    CFD_MAX_OPEN_PER_SYMBOL = 10
    conn = get_conn()
    open_count = conn.execute(
        "SELECT COUNT(*) FROM cfd_paper_trades WHERE symbol = ? AND result = 'OPEN'", (symbol,)
    ).fetchone()[0]
    if open_count >= CFD_MAX_OPEN_PER_SYMBOL:
        conn.close()
        print(f"[DB] Skip CFD trade: {symbol} already has {open_count} OPEN trades")
        return None
    ps = get_pip_size(symbol)
    spread = CFD_SPREAD_PIPS * ps
    eff = entry_price + spread / 2 if direction == "CALL" else entry_price - spread / 2
    lot = _cfd_lot_size(symbol)

    if direction == "CALL":
        sl = eff - CFD_SL_PIPS * ps
        tp1 = eff + CFD_TP1_PIPS * ps
        tp2 = eff + CFD_TP2_PIPS * ps
    else:
        sl = eff + CFD_SL_PIPS * ps
        tp1 = eff - CFD_TP1_PIPS * ps
        tp2 = eff - CFD_TP2_PIPS * ps

    cur = conn.execute(
        """INSERT INTO cfd_paper_trades
           (signal_id, signal_type, symbol, direction, entry_price, entry_time,
            sl_price, tp1_price, tp2_price, effective_entry, lot_size,
            pip_size, spread_pips, result)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')""",
        (
            signal_id,
            signal_type,
            symbol,
            direction,
            entry_price,
            entry_time,
            round(sl, 5),
            round(tp1, 5),
            round(tp2, 5),
            round(eff, 5),
            lot,
            ps,
            CFD_SPREAD_PIPS,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def fetch_open_cfd_trades() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM cfd_paper_trades WHERE result = 'OPEN' ORDER BY entry_time ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_cfd_result(
    cfd_id: int, result: str, exit_price: float, exit_time: str, hold_bars: int
) -> None:
    """บันทึกผล CFD trade: SL / TP1 (partial) / TP2 (full)"""
    conn = get_conn()
    row = conn.execute(
        "SELECT direction, effective_entry, lot_size, pip_size, spread_pips FROM cfd_paper_trades WHERE id = ?",
        (cfd_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return

    ps = row["pip_size"]
    lot = row["lot_size"]
    pv = 100.0 if ps >= 1.0 else 10.0
    spread_cost = row["spread_pips"] * ps * pv * lot
    risk_amt = CFD_SL_PIPS * pv * lot

    if result == "TP1":
        pnl = CFD_TP1_PIPS * pv * lot - spread_cost
    elif result == "TP2":
        pnl = CFD_TP2_PIPS * pv * lot - spread_cost
    else:
        pnl = -risk_amt - spread_cost

    conn.execute(
        """UPDATE cfd_paper_trades
           SET result = ?, exit_price = ?, exit_time = ?, hold_bars = ?, pnl = ?
           WHERE id = ?""",
        (result, round(exit_price, 5), exit_time, hold_bars, round(pnl, 2), cfd_id),
    )
    conn.commit()
    conn.close()


def fetch_cfd_stats() -> dict:
    """สถิติ CFD paper trading ทั้งหมด"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM cfd_paper_trades WHERE result != 'OPEN' ORDER BY exit_time ASC"
    ).fetchall()
    open_rows = conn.execute(
        "SELECT * FROM cfd_paper_trades WHERE result = 'OPEN' ORDER BY entry_time ASC"
    ).fetchall()
    conn.close()
    rows = [dict(r) for r in rows]
    open_rows = [dict(r) for r in open_rows]

    total = len(rows)
    sl_count = sum(1 for r in rows if r["result"] == "SL")
    tp1_count = sum(1 for r in rows if r["result"] == "TP1")
    tp2_count = sum(1 for r in rows if r["result"] == "TP2")
    total_pnl = sum(r["pnl"] or 0 for r in rows)

    by_type = {}
    for r in rows:
        st = r["signal_type"]
        if st not in by_type:
            by_type[st] = {"total": 0, "sl": 0, "tp1": 0, "tp2": 0, "pnl": 0.0}
        by_type[st]["total"] += 1
        by_type[st][r["result"].lower()] = by_type[st].get(r["result"].lower(), 0) + 1
        by_type[st]["pnl"] = round(by_type[st]["pnl"] + (r["pnl"] or 0), 2)

    by_dir = {}
    for r in rows:
        d = r["direction"]
        if d not in by_dir:
            by_dir[d] = {"total": 0, "sl": 0, "tp1": 0, "tp2": 0, "pnl": 0.0}
        by_dir[d]["total"] += 1
        by_dir[d][r["result"].lower()] = by_dir[d].get(r["result"].lower(), 0) + 1
        by_dir[d]["pnl"] = round(by_dir[d]["pnl"] + (r["pnl"] or 0), 2)

    for d in [*by_type.values(), *by_dir.values()]:
        d["wr"] = (
            round(100 * (d.get("tp1", 0) + d.get("tp2", 0)) / d["total"], 1) if d["total"] else 0.0
        )

    return {
        "total": total,
        "open": len(open_rows),
        "sl": sl_count,
        "tp1": tp1_count,
        "tp2": tp2_count,
        "wr": round(100 * (tp1_count + tp2_count) / total, 1) if total else 0.0,
        "total_pnl": round(total_pnl, 2),
        "by_type": by_type,
        "by_direction": by_dir,
        "trades": rows[-100:],
        "open_trades": open_rows,
    }


def check_cfd_trades(current_price: float, now_iso: str, symbol: str = "") -> list[dict]:
    """ตรวจ trades ที่ OPEN ของ symbol ที่ระบุ — คืน list ของ trades ที่เพิ่ง resolve
    Logic ใหม่: TP1 โดนแล้วไม่ปิด → ปล่อยวิ่งต่อ → TP2 = WIN, กลับลงมา = TP1 WIN"""
    open_trades = fetch_open_cfd_trades()
    if symbol:
        open_trades = [t for t in open_trades if t.get("symbol") == symbol]
    resolved = []
    for t in open_trades:
        d = t["direction"]
        sl = t["sl_price"]
        tp1 = t["tp1_price"]
        tp2 = t["tp2_price"]
        tp1_hit = t.get("tp1_hit", 0) or 0
        entry_t = pd.Timestamp(t["entry_time"])
        now_t = pd.Timestamp(now_iso)
        hold_bars = int((now_t - entry_t).total_seconds() / 60)

        if d == "CALL":
            hit_sl = current_price <= sl
            hit_tp1 = current_price >= tp1
            hit_tp2 = current_price >= tp2
        else:
            hit_sl = current_price >= sl
            hit_tp1 = current_price <= tp1
            hit_tp2 = current_price <= tp2

        result = None

        # SL โดน → ปิดทันที
        if hit_sl:
            result = "SL"

        # TP1 โดนครั้งแรก → ตั้ง tp1_hit=1 แต่ไม่ปิด ปล่อยวิ่งต่อ
        elif hit_tp1 and not tp1_hit:
            _update_tp1_hit(t["id"])
            continue

        # TP1 เคยโดนแล้ว (tp1_hit=1)
        elif tp1_hit:
            if hit_tp2:
                result = "TP2"
            elif hit_sl:
                result = "SL"
            elif d == "CALL" and current_price < tp1:
                result = "TP1"
            elif d == "PUT" and current_price > tp1:
                result = "TP1"

        if result:
            update_cfd_result(t["id"], result, current_price, now_iso, hold_bars)
            resolved.append(
                {
                    **t,
                    "result": result,
                    "exit_price": current_price,
                    "exit_time": now_iso,
                    "hold_bars": hold_bars,
                }
            )

    return resolved


def _update_tp1_hit(cfd_id: int) -> None:
    """บันทึกว่า TP1 โดนแล้ว (ยังไม่ปิด trade)"""
    conn = get_conn()
    conn.execute("UPDATE cfd_paper_trades SET tp1_hit = 1 WHERE id = ?", (cfd_id,))
    conn.commit()
    conn.close()


def _backfill_cfd_paper_trades():
    """สร้าง CFD paper trades สำหรับ signals ที่ยัง PENDING แต่ไม่มี CFD record
    จำกัดเฉพาะ signals ที่สร้างภายใน 1 ชั่วโมงล่าสุดเท่านั้น (ป้องกัน flood)"""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = get_conn()
    cfd_ids = {r[0] for r in conn.execute("SELECT signal_id FROM cfd_paper_trades").fetchall()}
    pending_setup = conn.execute(
        "SELECT id, symbol, direction, entry_price, signal_time "
        "FROM setup_signals WHERE result = 'PENDING' AND signal_time > ?",
        (cutoff,),
    ).fetchall()
    pending_ml = conn.execute(
        "SELECT id, symbol, direction, entry_price, signal_time "
        "FROM ml_signals WHERE result = 'PENDING' AND signal_time > ?",
        (cutoff,),
    ).fetchall()
    conn.close()

    count = 0
    for row in pending_setup:
        if row[0] not in cfd_ids:
            try:
                insert_cfd_paper_trade(
                    signal_id=row[0],
                    signal_type="SETUP",
                    symbol=row[1] or "frxXAUUSD",
                    direction=row[2],
                    entry_price=row[3],
                    entry_time=row[4],
                )
                count += 1
            except Exception:
                pass
    for row in pending_ml:
        if row[0] not in cfd_ids:
            try:
                insert_cfd_paper_trade(
                    signal_id=row[0],
                    signal_type="ML",
                    symbol=row[1] or "frxXAUUSD",
                    direction=row[2],
                    entry_price=row[3],
                    entry_time=row[4],
                )
                count += 1
            except Exception:
                pass
    if count:
        print(f"[DB] Backfilled {count} CFD paper trades (signals < 1h old)")
