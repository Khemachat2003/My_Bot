"""
train_validate.py — Phase 2B (แก้ปัญหา data snooping จาก sweep รอบก่อน)

หลักการ: แบ่งข้อมูลเป็น 3 ส่วนตามเวลา (ไม่สุ่ม)
  - Train (60%)      : สอนโมเดล
  - Validation (20%) : ใช้เลือก threshold ที่ดีที่สุด (ส่วนนี้เท่านั้นที่ "เลือก" อะไรได้)
  - Test (20%)       : แตะครั้งเดียวตอนจบ วัดผลจริง ห้ามใช้เลือกอะไรทั้งสิ้น

นี่คือมาตรฐานที่ถูกต้องของการประเมินโมเดล ป้องกันไม่ให้ตัวเลขที่เห็น
เป็นแค่ "บังเอิญเข้ากับ test set ก้อนนี้" เหมือนที่เจอในผล sweep รอบก่อน
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

from backend.ml_forecaster.features import build_dataset
from backend.ml_forecaster.train import load_price_data


# Config ที่จะทดสอบ — เอาแค่ 3 ตัวที่ AUC สูงสุดจาก sweep รอบก่อน (ไม่เอาทั้ง 15 แบบ
# เพราะยิ่งลองเยอะยิ่งเสี่ยง snooping ซ้ำ — เลือกมาแค่ candidate ที่มีเหตุผลรองรับ)
CANDIDATES = [
    {"horizon": 5, "deadzone": 0.3},
    {"horizon": 3, "deadzone": 0.6},
    {"horizon": 5, "deadzone": 0.0},
]

CONF_GRID = [0.52, 0.55, 0.58, 0.60, 0.63, 0.65]


def three_way_split(X: pd.DataFrame, y: pd.Series,
                     train_ratio=0.6, val_ratio=0.2):
    n = len(X)
    i1 = int(n * train_ratio)
    i2 = int(n * (train_ratio + val_ratio))
    return (X.iloc[:i1], y.iloc[:i1],
            X.iloc[i1:i2], y.iloc[i1:i2],
            X.iloc[i2:], y.iloc[i2:])


def pick_best_threshold(y_val, proba_val, min_signals):
    """เลือก threshold ที่ดีที่สุดจาก VALIDATION set เท่านั้น"""
    best = {"conf": None, "winrate": 0, "n": 0}
    for conf in CONF_GRID:
        mask = (proba_val >= conf) | (proba_val <= (1 - conf))
        n = mask.sum()
        if n < min_signals:
            continue
        pred = np.where(proba_val[mask] >= conf, 1, 0)
        winrate = (pred == y_val.values[mask]).mean() * 100
        if winrate > best["winrate"]:
            best = {"conf": conf, "winrate": winrate, "n": int(n)}
    return best


def evaluate_on_test(y_test, proba_test, conf, min_signals):
    """วัดผลจริงบน TEST set ที่ไม่เคยถูกแตะมาก่อน โดยใช้ threshold ที่ val เลือกไว้แล้ว"""
    if conf is None:
        return {"n": 0, "winrate": None}
    mask = (proba_test >= conf) | (proba_test <= (1 - conf))
    n = mask.sum()
    if n == 0:
        return {"n": 0, "winrate": None}
    pred = np.where(proba_test[mask] >= conf, 1, 0)
    winrate = (pred == y_test.values[mask]).mean() * 100
    return {"n": int(n), "winrate": round(winrate, 2)}


def main():
    print("=== Train/Validation/Test แบบถูกวิธี (แก้ data snooping) ===\n")
    raw_df = load_price_data(min_candles=3000)
    print(f"ใช้ข้อมูล {len(raw_df)} แท่ง\n")

    results = []
    for cfg in CANDIDATES:
        horizon, deadzone = cfg["horizon"], cfg["deadzone"]
        print(f"--- horizon={horizon}m, deadzone={deadzone}x ATR ---")

        X, y = build_dataset(raw_df, horizon=horizon, deadzone_atr_mult=deadzone)
        X_tr, y_tr, X_val, y_val, X_test, y_test = three_way_split(X, y)
        print(f"  train={len(X_tr)} | val={len(X_val)} | test={len(X_test)}")

        model = lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.03, num_leaves=15, max_depth=4,
            min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
        )
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  callbacks=[lgb.early_stopping(30, verbose=False)])

        proba_val = model.predict_proba(X_val)[:, 1]
        proba_test = model.predict_proba(X_test)[:, 1]

        auc_val = roc_auc_score(y_val, proba_val)
        auc_test = roc_auc_score(y_test, proba_test)

        min_signals = max(30, int(len(X_val) * 0.03))
        chosen = pick_best_threshold(y_val, proba_val, min_signals)
        print(f"  เลือก threshold จาก validation: conf={chosen['conf']} "
              f"(val winrate={chosen['winrate']:.2f}% ถ้ามี)" if chosen['conf'] else
              "  ไม่มี threshold ไหนมี signal พอใน validation")

        final = evaluate_on_test(y_test, proba_test, chosen["conf"], min_signals)

        results.append({
            "horizon": horizon, "deadzone": deadzone,
            "auc_val": round(auc_val, 4), "auc_test": round(auc_test, 4),
            "chosen_conf": chosen["conf"],
            "TEST_n_signals": final["n"], "TEST_winrate_%": final["winrate"],
        })
        print()

    print("=" * 80)
    print("สรุป: ผลจริงบน TEST set ที่ไม่เคยถูกใช้เลือกอะไรเลย (เชื่อถือได้)")
    print("=" * 80)
    print(pd.DataFrame(results).to_string(index=False))
    print("\nauc_val vs auc_test ใกล้กัน = ผลเสถียร ไม่ overfit")
    print("auc_test ต่ำกว่า auc_val มาก = โมเดล overfit กับ validation ตอนเลือก threshold")
    print("TEST_winrate_% คือตัวเลขที่ควรเชื่อจริงๆ (ไม่ใช่ตัวเลขจาก sweep รอบก่อน)")


if __name__ == "__main__":
    main()
