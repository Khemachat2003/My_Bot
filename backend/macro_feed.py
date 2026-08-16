"""
macro_feed.py — ดึง DXY (US Dollar Index) รายชั่วโมงจาก Yahoo เข้า DB
=====================================================================
ใช้เป็นข้อมูลสำหรับ Regime-Gate (shadow mode): ตอนยิงสัญญาณ FIRE จะคำนวณ
gold_1h_slope + dxy_slope_24 + dxy_rsi + agree แล้วบันทึก (ยังไม่บล็อก)

รัน 2 แบบ:
    -m backend.macro_feed            # loop ดึงทุก MACRO_POLL_MINUTES (60)
    -m backend.macro_feed --once     # ดึงครั้งเดียวแล้วจบ (ทดสอบ/backfill)

DXY = DX-Y.NYB (ICE) — Yahoo chart API ฟรี ไม่ต้อง token
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

from backend import db

YAHOO_SYMBOL = "DX-Y.NYB"
POLL_MINUTES = int(os.getenv("MACRO_POLL_MINUTES", "60"))
FETCH_DAYS = int(os.getenv("MACRO_FETCH_DAYS", "10"))   # ครั้งละกี่วัน (ข้อมูลมี 1 ชม.)


def _fetch_dxy_hourly(days: int) -> list[dict]:
    """ดึง DXY รายชั่วโมงย้อนหลัง days วัน จาก Yahoo → [{ts, dxy_close}]"""
    end = int(time.time())
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{YAHOO_SYMBOL}"
           f"?interval=1h&period1={start}&period2={end}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    close = res["indicators"]["quote"][0]["close"]
    out = []
    for t, c in zip(ts, close):
        if c is None:
            continue
        out.append({
            "ts": pd.Timestamp(t, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "dxy_close": float(c),
        })
    return out


def sync_once() -> int:
    """ดึงข้อมูลใหม่เข้าตาราง macro_1h (upsert) — คืนจำนวนแถวที่เขียน"""
    rows = _fetch_dxy_hourly(FETCH_DAYS)
    if not rows:
        print("[macro_feed] ไม่มีข้อมูลจาก Yahoo — ข้ามรอบนี้")
        return 0
    n = 0
    for r in rows:
        db.upsert_macro_dxy(r["ts"], r["dxy_close"])
        n += 1
    latest = db.fetch_latest_macro_dxy()
    print(f"[macro_feed] อัปเดต DXY {n} แถว | ล่าสุด "
          f"{latest['ts'][:16] if latest else '-'} = {latest['dxy_close'] if latest else '-'}")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="ดึงครั้งเดียวแล้วจบ")
    args = ap.parse_args()

    db.init_db()
    if args.once:
        sync_once()
        return

    print(f"[macro_feed] เริ่ม loop ดึง DXY ทุก {POLL_MINUTES} นาที "
          f"({FETCH_DAYS} วัน/ครั้ง) ...")
    while True:
        try:
            sync_once()
        except Exception:
            import traceback
            traceback.print_exc()
        time.sleep(POLL_MINUTES * 60)


if __name__ == "__main__":
    main()
