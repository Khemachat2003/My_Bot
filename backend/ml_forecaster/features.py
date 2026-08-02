"""
features.py — Phase 2B: สร้าง features + labels สำหรับ ML forecaster

แนวคิด: โมเดลไม่ได้ทำนายราคา (regression) เพราะยากและ noise สูงเกินไปสำหรับ
short-term option — แต่ทำนาย "ความน่าจะเป็นที่ราคาจะขึ้น" ในอีก N แท่งข้างหน้า
(binary classification) ซึ่งตรงกับสิ่งที่ต้องรู้จริงๆ ตอนซื้อ CALL/PUT
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.indicators import add_all_indicators


FEATURE_COLUMNS = [
    "rsi", "macd_line", "macd_signal", "macd_hist",
    "atr_pct", "bb_width", "adx", "stoch_k", "stoch_d",
    "body_size", "upper_wick", "lower_wick",
    "ema20_dist", "ema50_dist",
    "ret_1", "ret_3", "ret_5", "ret_10",
    "hour_sin", "hour_cos",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    รับ DataFrame แท่งเทียนดิบ (open/high/low/close/volume, index=datetime)
    คืนค่า DataFrame ที่มีคอลัมน์ indicators เดิม + feature เพิ่มเติมสำหรับ ML
    """
    df = add_all_indicators(df)

    c = df["close"]

    # ระยะห่างราคาปัจจุบันจาก EMA (normalize เป็น % จะได้ scale เดียวกันทุก timeframe)
    df["ema20_dist"] = (c - df["ema_20"]) / c * 100
    df["ema50_dist"] = (c - df["ema_50"]) / c * 100
    # หมายเหตุ: ตัด vwap_dist ออก เพราะ Deriv (frxXAUUSD) ไม่มี volume จริง
    # (ส่งมาเป็น 0 ทุกแท่ง) ทำให้สูตร VWAP หาร 0 กลายเป็น NaN ทั้งคอลัมน์

    # Momentum ระยะสั้น (return % ย้อนหลัง N แท่ง) — สำคัญมากสำหรับ option 1-5 นาที
    df["ret_1"]  = c.pct_change(1) * 100
    df["ret_3"]  = c.pct_change(3) * 100
    df["ret_5"]  = c.pct_change(5) * 100
    df["ret_10"] = c.pct_change(10) * 100

    # เวลาของวัน (session) มีผลกับ volatility ทองคำมาก — encode แบบ cyclical
    hour = df.index.hour + df.index.minute / 60.0
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)

    return df


def make_labels(
    df: pd.DataFrame,
    horizon: int = 5,
    deadzone_atr_mult: float = 0.0,
) -> pd.Series:
    """
    สร้าง label สำหรับ binary classification:
      1 = ราคาจะ "ขึ้น" ในอีก `horizon` แท่งข้างหน้า (เข้า CALL ถูก)
      0 = ราคาจะ "ลง" (เข้า PUT ถูก)
      NaN = ไม่ชัดเจนพอ (อยู่ใน deadzone) → ถูก drop ออกจาก training set

    horizon=5 กับแท่ง 1 นาที = ทำนายล่วงหน้า 5 นาที (option expiry สั้น)

    deadzone_atr_mult: ถ้า > 0 จะตัดแท่งที่ราคาขยับน้อยกว่า X * ATR ออก
    (สอนโมเดลจากเคสที่ "ชัดเจน" เท่านั้น ลด noise — แต่ตอน live inference
    โมเดลยังทำนายทุกแท่งได้ปกติ ไม่ใช้ deadzone ตอน predict)
    """
    future_close = df["close"].shift(-horizon)
    delta = future_close - df["close"]

    if deadzone_atr_mult > 0:
        threshold = df["atr"] * deadzone_atr_mult
        label = pd.Series(np.nan, index=df.index)
        label[delta > threshold] = 1
        label[delta < -threshold] = 0
    else:
        label = (delta > 0).astype(float)
        label[future_close.isna()] = np.nan

    return label


def build_dataset(
    df: pd.DataFrame,
    horizon: int = 5,
    deadzone_atr_mult: float = 0.0,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Entry point หลัก: raw OHLCV → (X features, y label) พร้อม train
    ตัดแถวที่มี NaN (จาก indicator warm-up period และ deadzone) ออกให้หมด
    """
    feat_df = build_features(df)
    y = make_labels(feat_df, horizon=horizon, deadzone_atr_mult=deadzone_atr_mult)

    X = feat_df[FEATURE_COLUMNS]
    valid = X.notna().all(axis=1) & y.notna()

    return X[valid], y[valid]
