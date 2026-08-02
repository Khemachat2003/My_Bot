"""
features_pa.py — Phase 4: price action / แนวรับ-แนวต้าน / เทรนด์เชิงเทคนิค

เพิ่มกลุ่ม feature ที่นักเทรดสาย technical analysis ใช้จริง แต่ยังไม่เคยอยู่ใน
features_v2.py มาก่อน (ของเดิมมีแค่ EMA/RSI/MACD/ADX/momentum เป็นหลัก):

  1. แนวรับ-แนวต้าน (support/resistance)
     - แบบ rolling channel (Donchian-style): highest-high / lowest-low ของ
       N แท่งล่าสุด "ไม่รวมแท่งปัจจุบัน" (shift(1)) กัน lookahead 100%
     - แบบ fractal pivot (ใช้ find_pivot_highs/lows ที่มีอยู่แล้วใน indicators.py
       แต่ไม่เคยถูกเรียกใช้ที่ไหนมาก่อน) — pivot ที่ index i ต้องรอ `right` แท่ง
       ถัดไปก่อนถึงจะ "รู้" ว่าเป็น pivot จริง เราจึง shift(right) แล้ว ffill
       ก่อนใช้ เพื่อไม่ให้โมเดลเห็นอนาคต
  2. เลขกลม (round-number levels) — ราคาทองมักมี psychological level ที่เลขกลม
     (เช่น 4000, 4050, 4100) ระยะห่างจากราคาปัจจุบันถึงเลขกลมที่ใกล้ที่สุด
  3. เทรนด์เชิงทิศทาง (+DI/-DI, ไม่ใช่แค่ ADX ที่บอกความแรงอย่างเดียว)
  4. แพทเทิร์นแท่งเทียนพื้นฐาน (engulfing, pin bar, doji) จาก body/wick ขนาดสัมพัทธ์

**กัน lookahead bias:** ทุก feature กลุ่มนี้ใช้ `.shift(1)` หรือเทียบเท่า
ก่อนนำมาใช้เป็น feature ของแท่งปัจจุบันเสมอ (ณ เวลา t เห็นได้แค่ข้อมูลถึง t-1
สำหรับ level/pivot ที่คำนวณจากข้อมูลในอดีต)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.indicators import find_pivot_highs, find_pivot_lows, directional_index


# ─── 1. Support / Resistance ─────────────────────────────────────────────────

def add_support_resistance_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    h, l, c = df["high"], df["low"], df["close"]

    for window in (20, 50, 100):
        res = h.rolling(window).max().shift(1)   # shift(1): ไม่รวมแท่งปัจจุบัน
        sup = l.rolling(window).min().shift(1)
        df[f"dist_to_res_{window}_pct"] = (res - c) / c * 100
        df[f"dist_to_sup_{window}_pct"] = (c - sup) / c * 100
        df[f"broke_res_{window}"] = (c > res).astype(int)   # breakout ทะลุแนวต้านเดิม
        df[f"broke_sup_{window}"] = (c < sup).astype(int)   # breakdown ทะลุแนวรับเดิม

    # fractal pivot (ยืนยันได้ก็ต่อเมื่อผ่านไปแล้ว `right` แท่ง — shift ก่อน ffill)
    left, right = 5, 5
    piv_high = find_pivot_highs(h, left=left, right=right).shift(right).ffill()
    piv_low = find_pivot_lows(l, left=left, right=right).shift(right).ffill()
    df["dist_to_pivot_high_pct"] = (piv_high - c) / c * 100
    df["dist_to_pivot_low_pct"] = (c - piv_low) / c * 100

    return df


SR_COLUMNS = (
    [f"dist_to_res_{w}_pct" for w in (20, 50, 100)]
    + [f"dist_to_sup_{w}_pct" for w in (20, 50, 100)]
    + [f"broke_res_{w}" for w in (20, 50, 100)]
    + [f"broke_sup_{w}" for w in (20, 50, 100)]
    + ["dist_to_pivot_high_pct", "dist_to_pivot_low_pct"]
)


# ─── 2. เลขกลม (round-number magnet levels) ──────────────────────────────────

def add_round_number_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    for step in (10, 50):
        nearest = (c / step).round() * step
        df[f"dist_to_round{step}_pct"] = (c - nearest).abs() / c * 100
    return df


ROUND_NUMBER_COLUMNS = ["dist_to_round10_pct", "dist_to_round50_pct"]


# ─── 3. เทรนด์เชิงทิศทาง (+DI / -DI) ──────────────────────────────────────────

def add_trend_direction_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    plus_di, minus_di = directional_index(df, period=14)
    df["di_diff"] = plus_di - minus_di          # >0 โน้มเอียงขาขึ้น, <0 ขาลง
    df["di_trend_bias"] = np.sign(df["di_diff"])
    if "adx" in df.columns:
        df["is_trending"] = (df["adx"] > 25).astype(int)   # ADX>25 = เทรนด์มีนัยสำคัญ (rule of thumb ทั่วไป)
    return df


TREND_DIRECTION_COLUMNS = ["di_diff", "di_trend_bias"]  # is_trending เพิ่มแบบมีเงื่อนไข ใส่แยกด้านล่าง


# ─── 4. แพทเทิร์นแท่งเทียนพื้นฐาน ─────────────────────────────────────────────

def add_candlestick_pattern_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    prev_o, prev_c = o.shift(1), c.shift(1)

    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    upper_wick = h - pd.concat([o, c], axis=1).max(axis=1)
    lower_wick = pd.concat([o, c], axis=1).min(axis=1) - l

    is_bull = c > o
    prev_is_bear = prev_c < prev_o

    df["bullish_engulfing"] = (
        is_bull & prev_is_bear & (c >= prev_o) & (o <= prev_c)
    ).astype(int)
    df["bearish_engulfing"] = (
        (~is_bull) & (~prev_is_bear) & (o >= prev_c) & (c <= prev_o)
    ).astype(int)

    df["pin_bar_bullish"] = ((lower_wick > 2 * body) & (upper_wick < body)).astype(int)
    df["pin_bar_bearish"] = ((upper_wick > 2 * body) & (lower_wick < body)).astype(int)
    df["doji"] = (body / rng < 0.1).astype(int)

    return df


CANDLE_PATTERN_COLUMNS = [
    "bullish_engulfing", "bearish_engulfing", "pin_bar_bullish", "pin_bar_bearish", "doji",
]


# ─── Entry point ──────────────────────────────────────────────────────────────

def add_price_action_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_support_resistance_features(df)
    df = add_round_number_features(df)
    df = add_trend_direction_features(df)
    df = add_candlestick_pattern_features(df)
    return df


PA_COLUMNS = (
    SR_COLUMNS + ROUND_NUMBER_COLUMNS + TREND_DIRECTION_COLUMNS
    + (["is_trending"] if True else []) + CANDLE_PATTERN_COLUMNS
)
