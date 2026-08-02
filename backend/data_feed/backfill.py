"""
backfill.py — Phase 2B (เสริม): สะสมข้อมูลย้อนหลังให้ได้มากกว่า 5000 แท่ง

ปัญหา: Deriv จำกัด count สูงสุด 5000 แท่งต่อ 1 request (ticks_history)
วิธีแก้: ดึงเป็นช่วงๆ ย้อนหลังไปเรื่อยๆ โดยระบุ start/end เป็น epoch เอง
         แล้วเอามาต่อกัน (concat) + ตัดที่ซ้ำออก (dedupe) + เก็บสะสมใน CSV เดิม

รันตรงๆ (ดึงย้อนหลัง 14 วันของข้อมูล 1 นาที ~ ประมาณ 20,000 แท่ง):
    python -m backend.data_feed.backfill --days 14

แนะนำ: รันซ้ำทุกวัน (เช่นตั้ง cron/Task Scheduler) จะได้ข้อมูลสะสมเพิ่มขึ้นเรื่อยๆ
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import websocket

from backend.data_feed.deriv_feed import DERIV_WS_URL, DEFAULT_SYMBOL, DATA_DIR


def fetch_chunk(symbol: str, granularity: int, end_epoch: int, count: int = 5000,
                 timeout: int = 15) -> pd.DataFrame:
    """ดึงแท่งเทียน count แท่ง นับถอยหลังจาก end_epoch (ใช้ synchronous connection ที่พิสูจน์แล้วว่าเสถียร)"""
    req = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": count,
        "end": end_epoch,
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
    return df


def backfill(
    symbol: str = DEFAULT_SYMBOL,
    granularity: int = 60,
    days: int = 14,
    chunk_size: int = 5000,
    pause_sec: float = 1.0,
) -> pd.DataFrame:
    """
    ดึงย้อนหลังทีละ chunk (5000 แท่ง) เรื่อยๆ จนครบจำนวนวันที่ต้องการ
    แล้วรวมกับ CSV เดิมที่มีอยู่ (ถ้ามี) — ไม่ทำให้ข้อมูลเก่าหาย
    """
    target_candles = int(days * 24 * 60 * 60 / granularity)
    print(f"[Backfill] เป้าหมาย: {days} วัน (~{target_candles} แท่ง) | granularity={granularity}s")

    all_chunks = []
    end_epoch = int(datetime.now(tz=timezone.utc).timestamp())
    collected = 0

    while collected < target_candles:
        remaining = target_candles - collected
        count = min(chunk_size, remaining)
        print(f"[Backfill] ดึง {count} แท่ง ก่อนเวลา "
              f"{datetime.fromtimestamp(end_epoch, tz=timezone.utc)} ...")

        chunk = fetch_chunk(symbol, granularity, end_epoch, count=count)
        if chunk.empty:
            print("[Backfill] ไม่มีข้อมูลเพิ่มแล้ว (ชนขอบเขตย้อนหลังสุดของ Deriv) หยุดดึง")
            break

        all_chunks.append(chunk)
        collected += len(chunk)
        end_epoch = int(chunk.index[0].timestamp()) - granularity  # ถอยไปก่อนแท่งแรกสุดที่ได้มา

        time.sleep(pause_sec)  # กันยิง request ถี่เกินไปจน Deriv จำกัด rate

    if not all_chunks:
        raise RuntimeError("ดึงข้อมูลไม่ได้เลยแม้แต่ chunk เดียว")

    new_df = pd.concat(all_chunks).sort_index()
    new_df = new_df[~new_df.index.duplicated(keep="first")]

    cache_path = DATA_DIR / f"deriv_{symbol}_{granularity}s.csv"
    if cache_path.exists():
        old_df = pd.read_csv(cache_path, index_col="datetime", parse_dates=True)
        combined = pd.concat([old_df, new_df]).sort_index()
        combined = combined[~combined.index.duplicated(keep="first")]
    else:
        combined = new_df

    combined.to_csv(cache_path)
    print(f"\n[Backfill] เสร็จสิ้น — รวมทั้งหมด {len(combined)} แท่ง "
          f"({combined.index[0]} → {combined.index[-1]})")
    print(f"[Backfill] บันทึกที่ {cache_path}")
    return combined


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14, help="จำนวนวันย้อนหลังที่ต้องการ")
    parser.add_argument("--granularity", type=int, default=60, help="วินาทีต่อแท่ง (60=1m)")
    args = parser.parse_args()

    backfill(days=args.days, granularity=args.granularity)
