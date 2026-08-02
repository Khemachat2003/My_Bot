"""
features_macro.py — Phase 5b: รวม correlated-asset context (DXY / US10Y / Silver)
เข้ากับแท่ง XAUUSD 1 นาที

ใช้ pattern เดียวกับ multi-timeframe ใน features_v2.py ทุกอย่าง (merge_asof
direction='backward') เพื่อกัน look-ahead bias เหมือนกัน — ณ เวลา t ใดๆ
โมเดลเห็นได้แค่แท่ง macro ที่ "ปิดสนิทแล้ว" เท่านั้น

ต้องรัน `python -m backend.data_feed.macro_feed --days N` ก่อน เพื่อสร้าง
CSV cache ให้ load_cached_macro() อ่านได้ (ฟีเจอร์กลุ่มนี้แยกออกมาจาก
features_v4.py เพราะต้องมี external data ก่อน ไม่ self-contained เหมือนกลุ่มอื่น)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.indicators import ema


def _macro_block(macro_df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    c = macro_df["close"]
    ema_fast, ema_slow = ema(c, 9), ema(c, 21)

    out = pd.DataFrame(index=macro_df.index)
    out[f"{prefix}_trend"] = np.sign(ema_fast - ema_slow)         # -1/0/1 ทิศทางเทรนด์
    out[f"{prefix}_chg_pct"] = c.pct_change(3) * 100               # % เปลี่ยนแปลง 3 แท่ง (3 ชม. ถ้า interval=60m)
    return out


def add_macro_features(df: pd.DataFrame, macro_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = df.copy()
    for name, macro_df in macro_data.items():
        block = _macro_block(macro_df, name)
        # yfinance index = เวลาเปิดแท่ง (left-labeled) ต้อง shift ไปเป็นเวลาปิดแท่งจริง
        # ก่อน merge_asof ไม่งั้น leak ข้อมูลของแท่งที่ยังไม่ปิดเข้าไปในราคาปัจจุบัน
        block = block.copy()
        block.index = block.index + pd.Timedelta(hours=1)  # interval=60m → เลื่อน 1 ชม.
        merged = pd.merge_asof(
            df.reset_index().sort_values("datetime"),
            block.reset_index().sort_values("datetime"),
            on="datetime",
            direction="backward",
        )
        df = merged.set_index("datetime")
    return df


def macro_columns(macro_data: dict[str, pd.DataFrame]) -> list[str]:
    cols = []
    for name in macro_data:
        cols += [f"{name}_trend", f"{name}_chg_pct"]
    return cols
