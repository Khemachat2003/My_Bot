"""
train_validate_v2.py — Phase 3: ทดสอบ feature set ใหม่ (multi-timeframe +
microstructure + session) เทียบกับของเดิม โดยยังคง 3-way split (train/val/test)
แบบเดียวกับ train_validate.py ทุกกฎ (ห้าม snoop, เลือก threshold จาก val เท่านั้น)

รัน:
    python -m backend.ml_forecaster.train_validate_v2

หมายเหตุ: ถ้าเครื่องไม่มี lightgbm ติดตั้ง (เช่น sandbox ทดสอบ) จะ fallback ไปใช้
sklearn HistGradientBoostingClassifier แทนโดยอัตโนมัติ — ผลลัพธ์จาก fallback
ใช้เป็น "สัญญาณเบื้องต้น" ได้ แต่ตัวเลขที่เชื่อถือได้จริงต้องรันด้วย LightGBM
บนเครื่อง user (Windows, venv เดิม) อีกครั้งเพื่อยืนยัน
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from pathlib import Path

from backend.ml_forecaster.features import build_dataset, FEATURE_COLUMNS as FEATURES_V1
from backend.ml_forecaster.features_v2 import build_dataset_v2, FEATURE_COLUMNS_V2, FEATURE_COLUMNS_V2_FULL

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False
    from sklearn.ensemble import HistGradientBoostingClassifier

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_price_data(min_candles: int = 3000) -> pd.DataFrame:
    """เหมือน train.py::load_price_data แต่ไม่ import lightgbm ที่ module level
    (กันปัญหาเครื่องที่ไม่มี lightgbm ติดตั้งพังตั้งแต่ import — ตัว fetch จริง
    ยังเรียก backend.data_feed.deriv_feed เหมือนเดิมถ้า cache ไม่พอ)
    """
    cache_path = DATA_DIR / "deriv_frxXAUUSD_60s.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, index_col="datetime", parse_dates=True)
        if len(df) >= min_candles:
            print(f"[Train] โหลด cache {cache_path} ({len(df)} แท่ง)")
            return df
        print(f"[Train] cache มีแค่ {len(df)} แท่ง (ต้องการ {min_candles}+) → ดึงใหม่จาก Deriv")

    from backend.data_feed.deriv_feed import fetch_candles_history
    return fetch_candles_history(granularity=60, count=min(min_candles, 5000))


CANDIDATES = [
    {"horizon": 5, "deadzone": 0.3},
    {"horizon": 3, "deadzone": 0.6},
    {"horizon": 5, "deadzone": 0.0},
    {"horizon": 15, "deadzone": 0.3},   # เพิ่ม horizon ยาวขึ้นด้วย เผื่อ multi-timeframe ช่วย horizon นี้มากกว่า
]

CONF_GRID = [0.52, 0.55, 0.58, 0.60, 0.63, 0.65, 0.68, 0.70]


def three_way_split(X: pd.DataFrame, y: pd.Series, train_ratio=0.6, val_ratio=0.2):
    n = len(X)
    i1 = int(n * train_ratio)
    i2 = int(n * (train_ratio + val_ratio))
    return (X.iloc[:i1], y.iloc[:i1],
            X.iloc[i1:i2], y.iloc[i1:i2],
            X.iloc[i2:], y.iloc[i2:])


def make_and_fit(X_tr, y_tr, X_val, y_val):
    if HAS_LGB:
        model = lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.03, num_leaves=15, max_depth=4,
            min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
        )
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                   callbacks=[lgb.early_stopping(30, verbose=False)])
    else:
        model = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.03, max_depth=4,
            min_samples_leaf=50, l2_regularization=0.1,
            random_state=42,
        )
        model.fit(X_tr, y_tr)
    return model


def pick_best_threshold(y_val, proba_val, min_signals):
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
    if conf is None:
        return {"n": 0, "winrate": None}
    mask = (proba_test >= conf) | (proba_test <= (1 - conf))
    n = mask.sum()
    if n == 0:
        return {"n": 0, "winrate": None}
    pred = np.where(proba_test[mask] >= conf, 1, 0)
    winrate = (pred == y_test.values[mask]).mean() * 100
    return {"n": int(n), "winrate": round(winrate, 2)}


def run_config(raw_df, horizon, deadzone, feature_set):
    if feature_set == "v1":
        X, y = build_dataset(raw_df, horizon=horizon, deadzone_atr_mult=deadzone)
    elif feature_set == "v2":
        X, y = build_dataset_v2(raw_df, horizon=horizon, deadzone_atr_mult=deadzone,
                                 feature_columns=FEATURE_COLUMNS_V2)
    else:  # v2_full
        X, y = build_dataset_v2(raw_df, horizon=horizon, deadzone_atr_mult=deadzone,
                                 feature_columns=FEATURE_COLUMNS_V2_FULL)

    X_tr, y_tr, X_val, y_val, X_test, y_test = three_way_split(X, y)
    if len(X_tr) < 200 or len(X_val) < 100 or len(X_test) < 100 or y_tr.nunique() < 2:
        return {"feature_set": feature_set, "horizon": horizon, "deadzone": deadzone,
                "n_rows": len(X), "auc_val": None, "auc_test": None,
                "chosen_conf": None, "TEST_n_signals": 0, "TEST_winrate_%": None}

    model = make_and_fit(X_tr, y_tr, X_val, y_val)
    proba_val = model.predict_proba(X_val)[:, 1]
    proba_test = model.predict_proba(X_test)[:, 1]

    auc_val = roc_auc_score(y_val, proba_val)
    auc_test = roc_auc_score(y_test, proba_test)

    min_signals = max(30, int(len(X_val) * 0.03))
    chosen = pick_best_threshold(y_val, proba_val, min_signals)
    final = evaluate_on_test(y_test, proba_test, chosen["conf"], min_signals)

    return {
        "feature_set": feature_set, "horizon": horizon, "deadzone": deadzone,
        "n_rows": len(X), "auc_val": round(auc_val, 4), "auc_test": round(auc_test, 4),
        "chosen_conf": chosen["conf"],
        "TEST_n_signals": final["n"], "TEST_winrate_%": final["winrate"],
    }


def main():
    print("=== Feature v1 (เดิม) vs v2 (multi-timeframe + microstructure + session) ===")
    print(f"Model backend: {'LightGBM' if HAS_LGB else 'sklearn HistGradientBoostingClassifier (fallback — lightgbm ไม่ได้ติดตั้งบนเครื่องนี้)'}\n")

    raw_df = load_price_data(min_candles=3000)
    print(f"ใช้ข้อมูล {len(raw_df)} แท่ง\n")

    results = []
    for cfg in CANDIDATES:
        for fset in ["v1", "v2", "v2_full"]:
            print(f"--- feature_set={fset}, horizon={cfg['horizon']}m, deadzone={cfg['deadzone']}x ATR ---")
            r = run_config(raw_df, cfg["horizon"], cfg["deadzone"], fset)
            flag = ""
            if r["auc_val"] is not None and r["auc_test"] is not None:
                if r["auc_val"] - r["auc_test"] > 0.02:
                    flag = "  ⚠️ val>>test = สัญญาณ overfit ตอนเลือก threshold ไม่ควรเชื่อ config นี้"
            print(f"  n_rows={r['n_rows']}  auc_val={r['auc_val']}  auc_test={r['auc_test']}  "
                  f"chosen_conf={r['chosen_conf']}  TEST_n={r['TEST_n_signals']}  TEST_winrate={r['TEST_winrate_%']}{flag}")
            results.append(r)
        print()

    df_res = pd.DataFrame(results)
    print("=" * 100)
    print("สรุปเทียบ v1 vs v2 (auc_test คือค่าที่เชื่อถือได้ — ไม่เคยถูกใช้เลือกอะไร)")
    print("=" * 100)
    print(df_res.to_string(index=False))

    print("\n── เทียบ auc_test เฉลี่ยต่อ feature set ──")
    print(df_res.groupby("feature_set")["auc_test"].mean())


if __name__ == "__main__":
    main()
