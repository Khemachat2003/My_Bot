"""
features_regime.py — Phase 5a: Volatility-regime features

ที่มา: mtf5/mtf15 (features_v2.py) พิสูจน์แล้วว่าช่วย (ติด top-3 importance)
ส่วน microstructure/session dummies ไม่ช่วย — สมมติฐานคือโมเดลยังไม่รู้ว่า
"ตอนนี้อยู่ใน regime ผันผวนแบบไหน" เทียบกับที่ผ่านมา (session dummy บอกแค่
"เวลาไหนของวัน" ไม่ได้บอกว่าตลาด "ผันผวนกว่าปกติของช่วงนั้นหรือเปล่า")

กลุ่มนี้ต่างจาก microstructure เดิมตรงที่เป็น "relative to history" ไม่ใช่
"absolute ของแท่งปัจจุบัน" — ให้โมเดลเห็นว่าความผันผวนตอนนี้อยู่ตรงไหนของ
การกระจายแบบยาวๆ (percentile rank) แทนที่จะเห็นแค่ atr_pct ดิบ

ทุกฟีเจอร์ใช้ rolling window ย้อนหลังเท่านั้น (ไม่มี lookahead)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_volatility_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """ต้องมีคอลัมน์ 'atr_pct' อยู่แล้ว (มาจาก build_features ใน features.py)"""
    df = df.copy()
    atr_pct = df["atr_pct"]

    # ตำแหน่งของ atr_pct ปัจจุบัน เทียบกับ distribution ย้อนหลัง (0=ต่ำสุด, 1=สูงสุด
    # ในหน้าต่างนั้น) — บอกว่า "ตอนนี้ผันผวนกว่าปกติของช่วงที่ผ่านมาแค่ไหน"
    # min_periods เท่ากับ window เพื่อกัน percentile ที่คำนวณจาก sample น้อยเกินไปตอน warm-up
    df["atr_rank_500"] = atr_pct.rolling(500, min_periods=500).rank(pct=True)
    df["atr_rank_2000"] = atr_pct.rolling(2000, min_periods=2000).rank(pct=True)

    # ความผันผวนกำลัง "ขยาย" หรือ "หด" อยู่ (เทียบ atr_pct ปัจจุบันกับ 20 แท่งก่อน)
    df["atr_expanding"] = np.sign(atr_pct - atr_pct.shift(20))

    # realized vol ของ return สั้นๆ เทียบ baseline ยาว (z-score) — ต่างจาก rvol_3/5/10
    # เดิมใน microstructure ตรงที่ normalize เทียบ history แทนที่จะเป็นค่าดิบ
    ret_1 = df["close"].pct_change(1) * 100
    rvol_short = ret_1.rolling(10).std()
    rvol_baseline_mean = rvol_short.rolling(500, min_periods=500).mean()
    rvol_baseline_std = rvol_short.rolling(500, min_periods=500).std()
    df["rvol_zscore"] = (rvol_short - rvol_baseline_mean) / rvol_baseline_std.replace(0, np.nan)

    return df


REGIME_COLUMNS = [
    "atr_rank_500", "atr_rank_2000", "atr_expanding", "rvol_zscore",
]
