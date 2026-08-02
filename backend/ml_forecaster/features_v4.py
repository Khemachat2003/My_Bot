"""
features_v4.py — Phase 5a: v1 + multi-timeframe (พิสูจน์แล้วว่าช่วยจาก v2)
+ volatility-regime ใหม่ (features_regime.py)

ตามธรรมเนียมเดิม: ไม่แก้ไฟล์เก่า เพิ่มไฟล์ใหม่แทน เพื่อ A/B เทียบกับทุก
feature set ก่อนหน้าได้เสมอผ่าน config_search.py

feature_set="regime"       → v1 + mtf + regime               (ชุดที่แนะนำให้ลองก่อน)
feature_set="regime_full"  → v1 + mtf + regime + price-action (รวมทุกอย่างที่พิสูจน์
                              แล้วว่าอย่างน้อยไม่เป็นลบชัดเจน + ของใหม่)
"""
from __future__ import annotations

import pandas as pd

from backend.ml_forecaster.features import make_labels, FEATURE_COLUMNS as FEATURE_COLUMNS_V1
from backend.ml_forecaster.features_v2 import build_features_v2, MTF_COLUMNS
from backend.ml_forecaster.features_regime import add_volatility_regime_features, REGIME_COLUMNS
from backend.ml_forecaster.features_pa import add_price_action_features, PA_COLUMNS

FEATURE_COLUMNS_REGIME = FEATURE_COLUMNS_V1 + MTF_COLUMNS + REGIME_COLUMNS
FEATURE_COLUMNS_REGIME_FULL = FEATURE_COLUMNS_V1 + MTF_COLUMNS + REGIME_COLUMNS + PA_COLUMNS


def build_features_v4(df: pd.DataFrame) -> pd.DataFrame:
    df = build_features_v2(df)               # v1 + mtf + microstructure + session (คำนวณไว้ทั้งหมดเหมือนเดิม)
    df = add_volatility_regime_features(df)   # + regime ใหม่
    df = add_price_action_features(df)        # + support/resistance ฯลฯ (เผื่อ regime_full)
    return df


def build_dataset_v4(
    df: pd.DataFrame,
    horizon: int = 5,
    deadzone_atr_mult: float = 0.0,
    feature_columns: list[str] | None = None,
):
    feat_df = build_features_v4(df)
    y = make_labels(feat_df, horizon=horizon, deadzone_atr_mult=deadzone_atr_mult)

    cols = feature_columns or FEATURE_COLUMNS_REGIME
    X = feat_df[cols]
    valid = X.notna().all(axis=1) & y.notna()

    return X[valid], y[valid]
