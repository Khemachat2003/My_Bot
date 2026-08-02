"""
confluence.py — Phase 2C: รวม ML forecaster + 3 strategies เดิม (strategies.py)

แนวคิด: ยิงสัญญาณเฉพาะตอนที่ "ทั้ง strategy เดิม (rule-based) และ ML เห็นตรงกัน"
เป้าหมายคือเพิ่มความแม่น (precision) แลกกับจำนวนสัญญาณที่น้อยลง
ซึ่งเหมาะกับ binary option ที่เราต้องการคุณภาพมากกว่าปริมาณอยู่แล้ว

ประเมินผลแบบยุติธรรม (เทียบ 3 วิธีบน TEST set เดียวกัน ไม่เคยถูกใช้เลือกอะไรมาก่อน):
  1. Strategy อย่างเดียว (baseline เดิม)
  2. ML อย่างเดียว (threshold 0.55 จากผลที่ validate แล้วว่า reproduce ได้จริง)
  3. Confluence (ต้องเห็นตรงกันทั้งคู่)

รัน:
    python -m backend.ml_forecaster.confluence
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

from backend.ml_forecaster.features import build_features, make_labels, FEATURE_COLUMNS
from backend.ml_forecaster.train import load_price_data
from backend.strategies import get_signal

# Config ที่พิสูจน์แล้วว่า reproduce ได้จริง (auc_val ≈ auc_test ≈ 0.535) จากขั้นก่อนหน้า
HORIZON = 5
DEADZONE_ATR_MULT = 0.3
ML_CONFIDENCE = 0.55


def three_way_split_index(n: int, train_ratio=0.6, val_ratio=0.2):
    i1 = int(n * train_ratio)
    i2 = int(n * (train_ratio + val_ratio))
    return i1, i2


def compute_strategy_directions(feat_df: pd.DataFrame) -> pd.Series:
    """
    ไล่ทุกแถวผ่าน get_signal() ของ strategies.py เดิม (rule-based)
    คืนค่า Series: 1=BUY, 0=SELL, NaN=NONE (ไม่มีสัญญาณ)
    """
    directions = pd.Series(np.nan, index=feat_df.index)
    rows = feat_df.to_dict("records")
    idx = feat_df.index

    for i in range(1, len(feat_df)):
        row = feat_df.iloc[i]
        prev = feat_df.iloc[i - 1]
        sig = get_signal(row, prev)
        if sig.direction == "BUY":
            directions.iloc[i] = 1
        elif sig.direction == "SELL":
            directions.iloc[i] = 0
        # NONE ปล่อยเป็น NaN

    return directions


def winrate_of(mask: np.ndarray, pred: np.ndarray, actual: np.ndarray) -> dict:
    n = int(mask.sum())
    if n == 0:
        return {"n_signals": 0, "winrate_%": None}
    wr = (pred[mask] == actual[mask]).mean() * 100
    return {"n_signals": n, "winrate_%": round(wr, 2)}


def main():
    print("=== Phase 2C: ML + Strategy Confluence ===\n")
    print(f"Config: horizon={HORIZON}m, deadzone={DEADZONE_ATR_MULT}x ATR, "
          f"ML confidence={ML_CONFIDENCE}\n")

    raw_df = load_price_data(min_candles=3000)
    print(f"ใช้ข้อมูล {len(raw_df)} แท่ง")

    print("\n[1/4] สร้าง features (indicators + ML features ในรอบเดียว)...")
    feat_df = build_features(raw_df)
    y_full = make_labels(feat_df, horizon=HORIZON, deadzone_atr_mult=DEADZONE_ATR_MULT)

    # เอาเฉพาะแถวที่ครบทั้ง feature และ label (เหมือน build_dataset แต่เก็บ feat_df เต็มไว้ใช้กับ strategy ด้วย)
    X_full = feat_df[FEATURE_COLUMNS]
    valid = X_full.notna().all(axis=1) & y_full.notna()
    feat_df = feat_df[valid]
    X_full = X_full[valid]
    y_full = y_full[valid]
    print(f"      ได้ {len(feat_df)} แถวใช้ได้")

    n = len(feat_df)
    i1, i2 = three_way_split_index(n)

    X_train, y_train = X_full.iloc[:i1], y_full.iloc[:i1]
    X_val, y_val = X_full.iloc[i1:i2], y_full.iloc[i1:i2]
    X_test, y_test = X_full.iloc[i2:], y_full.iloc[i2:]
    feat_test = feat_df.iloc[i2:]
    print(f"      train={len(X_train)} | val={len(X_val)} | test={len(X_test)} (test คือส่วนที่วัดผลจริง)")

    print("\n[2/4] เทรน ML model (บน train set เท่านั้น)...")
    model = lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.03, num_leaves=15, max_depth=4,
        min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(30, verbose=False)])

    proba_test = model.predict_proba(X_test)[:, 1]
    auc_test = roc_auc_score(y_test, proba_test)
    print(f"      AUC บน test set: {auc_test:.4f}")

    print("\n[3/4] รันสัญญาณจาก 3 strategies เดิม บน test set (ไล่ทีละแถว)...")
    strat_dir_test = compute_strategy_directions(feat_test)
    n_strategy_fired = strat_dir_test.notna().sum()
    print(f"      strategy เดิมยิงสัญญาณ {n_strategy_fired} ครั้ง "
          f"จาก {len(feat_test)} แถว ({n_strategy_fired/len(feat_test)*100:.1f}%)")

    print("\n[4/4] เปรียบเทียบ 3 วิธี บน test set เดียวกัน...\n")
    actual = y_test.values
    ml_pred_up = proba_test >= ML_CONFIDENCE
    ml_pred_down = proba_test <= (1 - ML_CONFIDENCE)
    ml_mask = ml_pred_up | ml_pred_down
    ml_pred = np.where(ml_pred_up, 1, 0)

    strat_mask = strat_dir_test.notna().values
    strat_pred = np.nan_to_num(strat_dir_test.values, nan=-1)

    confluence_mask = strat_mask & ml_mask & (strat_pred == ml_pred)
    # ทิศทางที่ confluence เห็นตรงกัน = เอา ml_pred (เท่ากับ strat_pred อยู่แล้วตรงจุดที่ mask=True)

    results = {
        "1) Strategy อย่างเดียว (baseline)": winrate_of(strat_mask, strat_pred, actual),
        "2) ML อย่างเดียว": winrate_of(ml_mask, ml_pred, actual),
        "3) Confluence (ต้องตรงกันทั้งคู่)": winrate_of(confluence_mask, ml_pred, actual),
    }

    summary = pd.DataFrame(results).T
    summary.index.name = "วิธี"
    print(summary.to_string())

    print("\n" + "=" * 70)
    print("วิธีอ่าน: ถ้า Confluence ให้ winrate_% สูงกว่าทั้ง 2 วิธีแรกอย่างชัดเจน")
    print("(และ n_signals ยังพอใช้งานได้ ไม่ใช่แค่หลักหน่วย) แปลว่าการรวมกันช่วยจริง")
    print("ถ้า n_signals ของ confluence น้อยเกินไป (เช่น <30 ใน test set นี้)")
    print("แปลว่าเงื่อนไขเข้มเกินไป ไม่มีทางปฏิบัติได้จริง ต้องผ่อนเงื่อนไขลง")
    print("=" * 70)


if __name__ == "__main__":
    main()
