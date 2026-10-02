"""db.prices — ราคา/กราฟ (ใช้ร่วมทั้ง 2 ระบบ) + ticks — ย้ายจาก db.py แบบ move-only"""

from __future__ import annotations

import pandas as pd

from backend.data_feed.deriv_feed import DEFAULT_SYMBOL
from backend.db.connection import MAX_PRICE_ROWS, MAX_TICK_ROWS, get_conn


# PRICES / TICKS (shared)
def insert_price(
    ts: str, open_: float, high: float, low: float, close: float, symbol: str | None = None
) -> None:
    symbol = symbol or DEFAULT_SYMBOL
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO prices (ts, symbol, open, high, low, close) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, symbol, open_, high, low, close),
    )
    conn.execute(
        """DELETE FROM prices WHERE ts NOT IN (
             SELECT ts FROM prices WHERE symbol = ? ORDER BY ts DESC LIMIT ?
           )""",
        (symbol, MAX_PRICE_ROWS),
    )
    conn.commit()
    conn.close()


def backfill_prices(candles, symbol: str | None = None) -> int:
    """เขียนแท่งเทียนย้อนหลังทั้งชุดลง prices ครั้งเดียว (ตอนเริ่มระบบ)

    เดิมทั้ง setup_feed/notifier แทรกแค่ "แท่งสุดท้าย" ต่อ poll → บนเครื่องใหม่
    (เช่น VPS เพิ่ง boot) ตาราง prices จะว่างเปล่าแล้วค่อยๆ งอกทีละแท่ง
    ทำให้กราฟ Dashboard แท่งเทียนว่าง/ไม่เต็มกรอบไปหลายชั่วโมง
    ฟังก์ชันนี้ bulk เขียนทุกแท่งใน buffer (เฉพาะที่ยังไม่มีในตาราง) ให้กราฟ
    มีประวัติทันที ใช้ INSERT OR REPLACE เพื่อให้ค่าแท่งล่าสุดถูกเสมอ
    """
    if candles is None or len(candles) == 0:
        return 0
    symbol = symbol or DEFAULT_SYMBOL
    rows = []
    for ts, r in candles.iterrows():
        ts_iso = pd.Timestamp(ts).isoformat()
        rows.append(
            (ts_iso, symbol, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]))
        )
    if not rows:
        return 0

    conn = get_conn()
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO prices (ts, symbol, open, high, low, close) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute(
            """DELETE FROM prices WHERE ts NOT IN (
                 SELECT ts FROM prices WHERE symbol = ? ORDER BY ts DESC LIMIT ?
               )""",
            (symbol, MAX_PRICE_ROWS),
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def insert_tick(timestamp_iso: str, price: float) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO ticks (timestamp, price) VALUES (?, ?)",
        (timestamp_iso, price),
    )
    conn.execute(
        """DELETE FROM ticks WHERE timestamp NOT IN (
             SELECT timestamp FROM ticks ORDER BY timestamp DESC LIMIT ?
           )""",
        (MAX_TICK_ROWS,),
    )
    conn.commit()
    conn.close()


def fetch_recent_prices(limit: int = 500, symbol: str | None = None) -> list[dict]:
    symbol = symbol or DEFAULT_SYMBOL
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM prices WHERE symbol = ? ORDER BY ts DESC LIMIT ?", (symbol, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows][::-1]


def fetch_last_prices(symbols: list[str], per_symbol: int = 2) -> dict[str, list[dict]]:
    """ราคาล่าสุดของหลาย symbol ใน query เดียว (สำหรับ watchlist)

    คืน {symbol: [{'c':..,'ts':..}, ...]} เรียงจากใหม่→เก่า
    ช่วยลด load ของ API: เดิม watchlist ยิง /api/candles 8 ครั้ง (หนึ่งต่อ symbol)
    → เหลือ 1 request
    """
    syms = [s for s in dict.fromkeys(symbols) if s]
    if not syms:
        return {}
    per_symbol = max(1, min(int(per_symbol), 5))
    part = (
        "SELECT * FROM (SELECT symbol, close, ts FROM prices "
        "WHERE symbol = ? ORDER BY ts DESC LIMIT ?)"
    )
    sql = " UNION ALL ".join([part] * len(syms))
    params: list = []
    for s in syms:
        params += [s, per_symbol]
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    out: dict[str, list[dict]] = {s: [] for s in syms}
    for r in rows:
        out.setdefault(r["symbol"], []).append({"c": r["close"], "ts": r["ts"]})
    return out
