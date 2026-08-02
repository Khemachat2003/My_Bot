"""
train_sweep.py — Phase 2B (วิจัยหา edge อย่างเป็นระบบ)

แทนที่จะเดาทีละ horizon/deadzone เอง สคริปต์นี้ลองหลาย config พร้อมกัน
บนข้อมูลชุดเดียวกัน แล้วสรุปเป็นตารางเดียวให้เทียบง่าย

รัน:
    python -m backend.ml_forecaster.train_sweep
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

from backend.ml_forecaster.features import build_dataset, FEATURE_COLUMNS
from backend.ml_forecaster.train import load_price_data, time_split


HORIZONS = [3, 5, 10, 15, 30]           # นาทีข้างหน้าที่จะทำนาย
DEADZONES = [0.0, 0.3, 0.6]             # ตัด label กำกวมออก (คูณ ATR) — 0 = ไม่ตัด


def run_one_config(raw_df: pd.DataFrame, horizon: int, deadzone: float) -> dict:
    X, y = build_dataset(raw_df, horizon=horizon, deadzone_atr_mult=deadzone)

    if len(X) < 500:
        return {"horizon": horizon, "deadzone": deadzone, "n_rows": len(X),
                "auc": None, "best_conf": None, "best_winrate": None, "best_n": None}

    X_train, X_test, y_train, y_test = time_split(X, y, test_ratio=0.2)
    if len(X_test) < 100 or y_train.nunique() < 2:
        return {"horizon": horizon, "deadzone": deadzone, "n_rows": len(X),
                "auc": None, "best_conf": None, "best_winrate": None, "best_n": None}

    model = lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.03, num_leaves=15, max_depth=4,
        min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)],
              callbacks=[lgb.early_stopping(30, verbose=False)])

    proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, proba)

    # หา confidence threshold ที่ดีที่สุดที่ยังมี coverage อย่างน้อย 3% ของ test set
    # (กันไม่ให้เลือก threshold ที่มีแค่ 2-3 สัญญาณแล้วดูเหมือนแม่น 100% ทั้งที่เป็น noise)
    best = {"conf": None, "winrate": 0, "n": 0}
    min_signals = max(30, int(len(y_test) * 0.03))
    for conf in [0.52, 0.55, 0.58, 0.60, 0.63, 0.65, 0.68, 0.70]:
        up_mask = proba >= conf
        down_mask = proba <= (1 - conf)
        mask = up_mask | down_mask
        n = mask.sum()
        if n < min_signals:
            continue
        pred = np.where(up_mask[mask], 1, 0)
        winrate = (pred == y_test.values[mask]).mean() * 100
        if winrate > best["winrate"]:
            best = {"conf": conf, "winrate": winrate, "n": int(n)}

    return {
        "horizon": horizon, "deadzone": deadzone, "n_rows": len(X),
        "auc": round(auc, 4),
        "best_conf": best["conf"], "best_winrate": round(best["winrate"], 2) if best["conf"] else None,
        "best_n": best["n"] if best["conf"] else None,
    }


def main():
    print("=== Sweep: หา config (horizon x deadzone) ที่มี edge จริง ===\n")
    raw_df = load_price_data(min_candles=3000)
    print(f"ใช้ข้อมูล {len(raw_df)} แท่ง\n")

    results = []
    for horizon in HORIZONS:
        for deadzone in DEADZONES:
            print(f"[Sweep] horizon={horizon}m, deadzone={deadzone}x ATR ...")
            r = run_one_config(raw_df, horizon, deadzone)
            results.append(r)

    df = pd.DataFrame(results)
    print("\n" + "=" * 80)
    print("สรุปผลทุก config (เรียงตาม AUC มากไปน้อย):")
    print("=" * 80)
    df_sorted = df.sort_values("auc", ascending=False, na_position="last")
    print(df_sorted.to_string(index=False))

    print("\nวิธีอ่าน:")
    print("- auc > 0.55 ถือว่าเริ่มมีนัยสำคัญ (0.50 = สุ่ม, 1.0 = ทำนายถูกทุกครั้ง)")
    print("- best_winrate ต้อง > 58% ขึ้นไปถึงจะคุ้มค่าธรรมเนียม/payout ของ binary option")
    print("- best_n ต้องมีพอสมควร (ไม่ใช่แค่ไม่กี่สิบตัว) ถึงจะเชื่อตัวเลขได้")
    print("- ถ้าทุก config ยังไม่ผ่านเกณฑ์ = ต้องกลับไปคิด feature ใหม่ ไม่ใช่แค่จูน hyperparameter")


if __name__ == "__main__":
    main()
