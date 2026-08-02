"""
features_v3.py — Phase 4: รวม feature เดิม (v1 + multi-timeframe จาก v2) เข้ากับ
กลุ่ม price-action/แนวรับ-แนวต้าน/เทรนด์เชิงทิศทาง/แพทเทิร์นแท่งเทียนใหม่ (features_pa.py)

ทำตามธรรมเนียมเดิมของโปรเจกต์ (ไม่แก้ features.py/features_v2.py เดิม เผื่อต้อง
A/B เทียบกับของเก่าเสมอ) — เพิ่มไฟล์ใหม่แทน
"""
from __future__ import annotations

import pandas as pd

from backend.ml_forecaster.features import make_labels, FEATURE_COLUMNS as FEATURE_COLUMNS_V1
from backend.ml_forecaster.features_v2 import (
    build_features_v2, MTF_COLUMNS, MICROSTRUCTURE_COLUMNS, SESSION_COLUMNS,
)
from backend.ml_forecaster.features_pa import add_price_action_features, PA_COLUMNS


def build_features_v3(df: pd.DataFrame) -> pd.DataFrame:
    df = build_features_v2(df)          # v1 + mtf + microstructure + session (คำนวณไว้ทั้งหมด)
    df = add_price_action_features(df)  # + support/resistance, round-number, di_trend, candle pattern
    return df


# ชุดที่แนะนำให้ลองก่อน: v1 + mtf (กลุ่มที่พิสูจน์แล้วว่าช่วยจาก v2) + price-action ใหม่
FEATURE_COLUMNS_PA = FEATURE_COLUMNS_V1 + MTF_COLUMNS + PA_COLUMNS

# ชุดรวมทุกอย่างที่มี (เผื่อ microstructure/session ที่เคยดูไม่ช่วยตอน 21 วัน
# จะช่วยขึ้นบ้างตอนนี้ข้อมูลเยอะขึ้นมาก — ต้องทดสอบใหม่ ไม่ควรเชื่อผลเก่า)
FEATURE_COLUMNS_PA_FULL = (
    FEATURE_COLUMNS_V1 + MTF_COLUMNS + MICROSTRUCTURE_COLUMNS + SESSION_COLUMNS + PA_COLUMNS
)


def build_dataset_v3(
    df: pd.DataFrame,
    horizon: int = 5,
    deadzone_atr_mult: float = 0.0,
    feature_columns: list[str] | None = None,
):
    feat_df = build_features_v3(df)
    y = make_labels(feat_df, horizon=horizon, deadzone_atr_mult=deadzone_atr_mult)

    cols = feature_columns or FEATURE_COLUMNS_PA
    X = feat_df[cols]
    valid = X.notna().all(axis=1) & y.notna()

    return X[valid], y[valid]
