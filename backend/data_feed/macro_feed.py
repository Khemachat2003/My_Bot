"""
macro_feed.py — Phase 5b: ดึงข้อมูล asset ที่สัมพันธ์กับทองคำ (correlated assets)
เพื่อใช้เป็น regime/context feature เพิ่มเติมจาก XAUUSD เดี่ยวๆ

ทำไมต้องมี: XAUUSD เพียงตัวเดียวไม่มี "เหตุผลว่าทำไมราคาขยับ" ให้โมเดลเห็น
แต่ทองคำมีความสัมพันธ์ (ไม่สมบูรณ์แบบ แต่มีนัยสำคัญ) กับ:
  - DXY (Dollar Index)     — ทองคำมักขยับสวนทางดอลลาร์แข็ง/อ่อน
  - US10Y yield            — real yield สูง = cost of holding gold สูง = กดดันราคาทอง
  - Silver (correlated commodity) — บางช่วง lead/lag ทองคำ (risk sentiment ร่วม)

ใช้ yfinance (มีอยู่แล้วใน venv ของโปรเจกต์) — เป็น data ฟรี ไม่ต้อง API key
ดึงที่ granularity 1 ชั่วโมง (ไม่ใช่ 1 นาที) เพราะ:
  1) yfinance free tier ให้ข้อมูล intraday 1m ย้อนหลังได้แค่ ~7 วัน แต่ 1h ย้อนหลังได้เป็นเดือน/ปี
  2) ความสัมพันธ์ macro พวกนี้เป็น regime-level อยู่แล้ว ไม่จำเป็นต้อง granular เท่า 1 นาที
     (จะ merge เข้า XAUUSD 1 นาทีแบบ backward-fill เหมือน multi-timeframe ใน features_v2.py)

รัน:
    python -m backend.data_feed.macro_feed --days 60
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ticker บน Yahoo Finance — DX-Y.NYB บางทีข้อมูลไม่ครบ ถ้าใช้ไม่ได้ให้ลอง "UUP" (Dollar ETF) แทน
MACRO_TICKERS = {
    "dxy": "DX-Y.NYB",
    "us10y": "^TNX",
    "silver": "SI=F",
}


def fetch_macro(days: int = 60, interval: str = "60m") -> dict[str, pd.DataFrame]:
    """คืน dict {name: DataFrame(open/high/low/close, index=datetime UTC)}
    ดึงทีละ ticker แยกกัน เพื่อให้ ticker หนึ่งดึงไม่ได้ไม่ทำให้ตัวอื่นพังไปด้วย
    """
    import yfinance as yf  # import ตรงนี้ ไม่ใช่บนสุดของไฟล์ กันพังตอน import ถ้ายังไม่ได้ pip install

    out = {}
    for name, ticker in MACRO_TICKERS.items():
        print(f"[Macro] ดึง {name} ({ticker}) ย้อนหลัง {days} วัน interval={interval} ...")
        try:
            hist = yf.Ticker(ticker).history(period=f"{days}d", interval=interval)
            if hist.empty:
                print(f"[Macro] ⚠️ {name} ({ticker}) ได้ข้อมูลว่างเปล่า — ข้าม")
                continue
            hist.index = pd.to_datetime(hist.index, utc=True)
            df = hist[["Open", "High", "Low", "Close"]].rename(
                columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"}
            )
            df.index.name = "datetime"
            cache_path = DATA_DIR / f"macro_{name}_{interval}.csv"
            df.to_csv(cache_path)
            print(f"[Macro] {name}: {len(df)} แท่ง ({df.index[0]} → {df.index[-1]}) → {cache_path}")
            out[name] = df
        except Exception as e:
            print(f"[Macro] ⚠️ ดึง {name} ({ticker}) ไม่สำเร็จ: {e} — ข้าม (ตัวอื่นดึงต่อได้ปกติ)")
    return out


def load_cached_macro(interval: str = "60m") -> dict[str, pd.DataFrame]:
    """โหลดจาก CSV ที่ backfill ไว้แล้ว (ไม่ยิง network) — ใช้ตอนรัน config_search/feature build"""
    out = {}
    for name in MACRO_TICKERS:
        cache_path = DATA_DIR / f"macro_{name}_{interval}.csv"
        if cache_path.exists():
            out[name] = pd.read_csv(cache_path, index_col="datetime", parse_dates=True)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--interval", type=str, default="60m")
    args = parser.parse_args()
    fetch_macro(days=args.days, interval=args.interval)
