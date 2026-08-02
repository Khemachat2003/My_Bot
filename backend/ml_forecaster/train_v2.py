"""
train_v2.py — Phase 3: เทรนโมเดล production พร้อมระบบจัดการ Path และ Cache
"""
from __future__ import annotations

import sys
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# --- 1. บังคับเพิ่ม Root Directory ลงใน sys.path เพื่อป้องกัน ModuleNotFoundError ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import joblib
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

from backend.ml_forecaster.features_v2 import build_dataset_v2, FEATURE_COLUMNS_V2
from backend.ml_forecaster.train_validate_v2 import three_way_split, pick_best_threshold, evaluate_on_test

MODEL_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODEL_DIR / "model_v2.joblib"
DATA_DIR = ROOT_DIR / "data"

HORIZON = 5
DEADZONE = 0.3


def safe_load_price_data(min_candles: int = 3000) -> pd.DataFrame:
    """โหลดราคาจาก Cache CSV ถ้าดึงจาก Deriv ไม่ได้ ให้ใช้เท่าที่มีใน Cache แทน"""
    cache_path = DATA_DIR / "deriv_frxXAUUSD_60s.csv"
    
    if cache_path.exists():
        df = pd.read_csv(cache_path, index_col="datetime", parse_dates=True)
        if len(df) >= min_candles:
            print(f"[Train] โหลด Cache สำเร็จ ({len(df)} แท่ง)")
            return df
        print(f"[Train] Cache มี {len(df)} แท่ง (น้อยกว่า {min_candles}) → พยายามดึงใหม่จาก Deriv API...")
    else:
        df = pd.DataFrame()

    # ลอง import deriv_feed โดยรองรับกรณีที่ชื่อไฟล์/โฟลเดอร์ไม่ตรง
    try:
        from backend.data_feed.deriv_feed import fetch_candles_history
        new_df = fetch_candles_history(granularity=60, count=min_candles)
        if len(new_df) > 0:
            return new_df
    except (ImportError, ModuleNotFoundError) as e:
        print(f"⚠️ [Warning] ดึงข้อมูลสดจาก Deriv ไม่สำเร็จ ({e})")
        print("💡 กำลังสลับไปใช้ข้อมูล Cache เท่าที่มีในเครื่องเพื่อเทรนไปก่อน...")

    if not df.empty:
        print(f"[Train] คืนค่าข้อมูลจาก Cache จำนวน {len(df)} แท่ง")
        return df

    raise FileNotFoundError(f"ไม่พบไฟล์ข้อมูลที่ {cache_path} และไม่สามารถดึงข้อมูลใหม่ได้")


def main():
    print("=== เทรนโมเดล production (v2: multi-timeframe features) ===\n")

    raw_df = safe_load_price_data(min_candles=3000)
    print(f"ใช้ข้อมูลทั้งหมด {len(raw_df)} แท่งในการทำ Features\n")

    X, y = build_dataset_v2(
        raw_df, 
        horizon=HORIZON, 
        deadzone_atr_mult=DEADZONE,
        feature_columns=FEATURE_COLUMNS_V2
    )
    print(f"ได้ {len(X)} แถวที่ใช้เทรนได้\n")

    # 1. แบ่ง Train / Validation / Test
    X_tr, y_tr, X_val, y_val, X_test, y_test = three_way_split(X, y)

    eval_model = lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.03, num_leaves=15, max_depth=4,
        min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
    )
    eval_model.fit(
        X_tr, y_tr, eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(30, verbose=False)]
    )

    proba_val = eval_model.predict_proba(X_val)[:, 1]
    proba_test = eval_model.predict_proba(X_test)[:, 1]

    auc_val = roc_auc_score(y_val, proba_val)
    auc_test = roc_auc_score(y_test, proba_test)

    # 2. คำนวณหา Best Threshold จาก Validation Set (Dynamic)
    min_signals = max(15, int(len(X_val) * 0.03))  # ปรับ min_signals ให้เหมาะกับข้อมูลขนาดเล็ก
    best_thresh_info = pick_best_threshold(y_val, proba_val, min_signals)
    dynamic_conf = best_thresh_info["conf"] if best_thresh_info["conf"] is not None else 0.55
    
    test_eval = evaluate_on_test(y_test, proba_test, dynamic_conf, min_signals)

    print(f"📊 Validation Results Summary:")
    print(f"   - AUC Val  : {auc_val:.4f}")
    print(f"   - AUC Test : {auc_test:.4f}")
    print(f"   - Selected Dynamic Threshold : {dynamic_conf}")
    print(f"   - Test Set Winrate @ Conf {dynamic_conf} : {test_eval['winrate']}% (Signals = {test_eval['n']})\n")

    # 3. เทรนโมเดล Final Production
    final_model = lgb.LGBMClassifier(
        n_estimators=eval_model.best_iteration_ or 300,
        learning_rate=0.03, num_leaves=15, max_depth=4,
        min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
    )
    final_model.fit(X, y)

    # 4. บันทึก Model Bundle
    joblib.dump({
        "model": final_model,
        "features": FEATURE_COLUMNS_V2,
        "horizon": HORIZON,
        "deadzone_atr_mult": DEADZONE,
        "chosen_conf": dynamic_conf,
        "sanity_auc_val": auc_val,
        "sanity_auc_test": auc_test,
    }, MODEL_PATH)

    print(f"✅ บันทึกโมเดล production เรียบร้อย → {MODEL_PATH}")
    print(f"   Threshold สำหรับ notifier.py: conf={dynamic_conf}")


if __name__ == "__main__":
    main()