"""db.macro — DXY รายชั่วโมง (Regime-Gate) — ย้ายจาก db.py แบบ move-only"""

from __future__ import annotations

from backend.db.connection import get_conn


def upsert_macro_dxy(ts: str, dxy_close: float) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO macro_1h (ts, dxy_close) VALUES (?, ?) "
        "ON CONFLICT(ts) DO UPDATE SET dxy_close = excluded.dxy_close",
        (ts, float(dxy_close)),
    )
    conn.commit()
    conn.close()


def fetch_macro_dxy(limit: int = 96) -> list[dict]:
    """DXY รายชั่วโมง เก่า→ใหม่ (limit แถวล่าสุด) — ใช้คำนวณ slope/RSI ตอนยิงสัญญาณ"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM macro_1h ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def fetch_latest_macro_dxy() -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM macro_1h ORDER BY ts DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None
