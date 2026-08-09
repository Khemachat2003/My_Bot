"""
fetch_history_paginated.py — ดึงราคาย้อนหลังจาก Deriv หลายเดือนแบบต่อเนื่อง (pagination)
======================================================================================
ทำไมต้องมีไฟล์นี้: deriv_feed.fetch_candles_history() ดึงได้ครั้งละสูงสุด ~5000 แท่ง
(M1 ≈ 3.5 วัน) ต่อ request เดียว ไม่พอสำหรับ backtest ที่น่าเชื่อถือ ไฟล์นี้เลยยิง
request วนไปเรื่อยๆ โดยขยับ "end" ให้ย้อนไปก่อนแท่งที่เก่าที่สุดของรอบก่อนหน้าทุกครั้ง
จนกว่าจะได้ข้อมูลครบตามจำนวนวันที่ขอ (หรือ Deriv ไม่มีข้อมูลเก่ากว่านี้ให้แล้ว)

วิธีใช้:
    python fetch_history_paginated.py --symbol frxXAUUSD --granularity 60 --days 90
    python fetch_history_paginated.py --symbol frxXAUUSD --granularity 300 --days 180

ผลลัพธ์: บันทึกเป็น CSV คอลัมน์ datetime,open,high,low,close,volume — ใช้กับ
    setup_backtest.py --csv <ไฟล์นี้> ได้ทันที
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import websocket  # pip install websocket-client

DERIV_WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"
MAX_BATCH = 5000       # ขีดจำกัดของ Deriv ต่อ request (ตามที่ fetch_candles_history เดิมใช้)
SAFETY_MAX_LOOPS = 400  # กันลูปไม่รู้จบถ้า Deriv ตอบวนซ้ำผิดปกติ


def _request_batch(symbol: str, granularity: int, end_epoch, count: int, timeout: int = 15) -> pd.DataFrame:
    req = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": count,
        "end": "latest" if end_epoch is None else str(end_epoch),
        "start": 1,
        "style": "candles",
        "granularity": granularity,
    }
    ws = websocket.create_connection(DERIV_WS_URL, timeout=timeout)
    try:
        ws.send(json.dumps(req))
        raw = ws.recv()
    finally:
        ws.close()

    data = json.loads(raw)
    if data.get("error"):
        raise RuntimeError(f"Deriv API error: {data['error']}")
    if "candles" not in data or not data["candles"]:
        return pd.DataFrame()

    df = pd.DataFrame(data["candles"])
    df["datetime"] = pd.to_datetime(df["epoch"], unit="s", utc=True)
    df["volume"] = 0.0
    df = df.set_index("datetime")[["open", "high", "low", "close", "volume"]].astype(float)
    return df.sort_index()


def fetch_history(symbol: str, granularity: int, target_days: int,
                   pause_sec: float = 1.0, batch_size: int = MAX_BATCH) -> pd.DataFrame:
    target_seconds = target_days * 86400
    all_batches = []
    end_epoch = None  # None = "latest" สำหรับรอบแรก
    seen_earliest = None
    total_span = 0

    for loop_i in range(SAFETY_MAX_LOOPS):
        print(f"  ดึงรอบที่ {loop_i + 1} ... (end={'latest' if end_epoch is None else end_epoch})", flush=True)
        try:
            batch = _request_batch(symbol, granularity, end_epoch, batch_size)
        except Exception as e:
            print(f"  ⚠️  รอบนี้ error: {e} — หยุดและใช้ข้อมูลที่มีอยู่แทน")
            break

        if batch.empty:
            print("  ไม่มีข้อมูลเพิ่มแล้ว (Deriv ไม่มีประวัติเก่ากว่านี้ให้) — หยุดดึง")
            break

        earliest = batch.index[0]
        if seen_earliest is not None and earliest >= seen_earliest:
            print("  ⚠️  ได้ช่วงเวลาเดิมซ้ำ (ไม่ขยับย้อนหลังต่อแล้ว) — หยุดดึงกันลูปค้าง")
            break
        seen_earliest = earliest

        all_batches.append(batch)
        total_span = (all_batches[-1].index[-1] if len(all_batches) == 1 else all_batches[0].index[-1]) - earliest
        combined_so_far = pd.concat(all_batches).sort_index()
        combined_so_far = combined_so_far[~combined_so_far.index.duplicated(keep="first")]
        span_now = (combined_so_far.index[-1] - combined_so_far.index[0]).total_seconds()
        print(f"    ได้ {len(batch)} แท่งเพิ่ม | สะสมรวม {len(combined_so_far)} แท่ง "
              f"| ครอบคลุม {span_now/86400:.1f} วัน | เก่าสุดตอนนี้ {earliest}", flush=True)

        if span_now >= target_seconds:
            print(f"  ครบ {target_days} วันตามที่ขอแล้ว หยุดดึง")
            break

        end_epoch = int(earliest.timestamp()) - granularity
        time.sleep(pause_sec)

    if not all_batches:
        raise RuntimeError("ดึงข้อมูลไม่ได้เลยสักรอบ — เช็ค symbol/granularity หรือการเชื่อมต่อเน็ต")

    full = pd.concat(all_batches).sort_index()
    full = full[~full.index.duplicated(keep="first")]
    return full


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ดึงราคาย้อนหลังจาก Deriv หลายเดือนแบบต่อเนื่อง")
    parser.add_argument("--symbol", type=str, default="frxXAUUSD")
    parser.add_argument("--granularity", type=int, default=60,
                         help="วินาทีต่อแท่ง: 60=1m, 300=5m, 900=15m")
    parser.add_argument("--days", type=int, default=90, help="จำนวนวันย้อนหลังที่ต้องการ")
    parser.add_argument("--pause", type=float, default=1.0,
                         help="วินาทีที่รอระหว่างแต่ละ request (กันโดน rate-limit)")
    parser.add_argument("--out", type=str, default=None,
                         help="path ไฟล์ CSV ที่จะบันทึก (ถ้าไม่ใส่ จะตั้งชื่ออัตโนมัติ)")
    args = parser.parse_args()

    print(f"เริ่มดึง {args.symbol} granularity={args.granularity}s ย้อนหลัง {args.days} วัน ...\n")
    df = fetch_history(args.symbol, args.granularity, args.days, pause_sec=args.pause)

    out_path = Path(args.out) if args.out else Path(
        f"deriv_{args.symbol}_{args.granularity}s_{args.days}d.csv"
    )
    df.to_csv(out_path)

    actual_days = (df.index[-1] - df.index[0]).total_seconds() / 86400
    print(f"\n✅ เสร็จแล้ว: {len(df)} แท่ง | {df.index[0]} → {df.index[-1]} "
          f"(~{actual_days:.1f} วัน)")
    print(f"บันทึกไว้ที่: {out_path.resolve()}")
    print(f"\nรัน backtest ต่อได้เลย:\n  python setup_backtest.py --csv \"{out_path.resolve()}\"")
