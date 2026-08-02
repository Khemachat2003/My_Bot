"""
train_live_models.py — เทรนโมเดล production แยกตาม timeframe ให้ตรงกับเวลาถือออเดอร์
=====================================================================================
ทำไมต้องมี: เดิมเทรน horizon=5 (พยากรณ์ 5 นาที) แต่ระบบถือออเดอร์ 15/30 นาที
ทำให้ confidence ที่ยิงออกมาไม่ได้หมายถึง "โอกาสชนะที่เวลาถือจริง" — สำหรับเทรดแบบ
option (Rise/Fall) ต้องให้ horizon ของโมเดลเท่ากับอายุของ option

สิ่งที่เทรน:
    model_m1.joblib  ← แท่ง 1m, horizon=15 แท่ง = ถือ 15 นาที
    model_m5.joblib  ← แท่ง 5m, horizon=6 แท่ง = ถือ 30 นาที

วิธีใช้:
    python -m backend.ml_forecaster.train_live_models                # ใช้ข้อมูลที่มีในเครื่อง
    python -m backend.ml_forecaster.train_live_models --fetch-days 60  # ดึงข้อมูลใหม่ก่อนเทรน
    python -m backend.ml_forecaster.train_live_models --retrain       # บังคับเทรนใหม่ (ลบโมเดลเก่า)

คำแนะนำ: ยิ่งมีข้อมูลเยอะโมเดลยิ่งแม่น — ควรมีอย่างน้อย 30-90 วัน (M1) ข้อมูล 2-3 วัน
ที่ผ่านมาให้ผล AUC ต่ำมาก (ใกล้ 0.5) เหมือนที่เห็นอยู่ตอนนี้
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")

# ป้องกัน print ภาษาไทย/emoji แล้ว crash เมื่อ console เป็น cp1252
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from backend.ml_forecaster.features_v2 import build_dataset_v2, FEATURE_COLUMNS_V2
from backend.ml_forecaster.train_validate_v2 import (
    three_way_split, make_and_fit, pick_best_threshold, evaluate_on_test,
)

MODEL_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

HORIZON_M1 = 15      # M1: พยากรณ์ 15 นาทีข้างหน้า = ถือ 15 นาที
HORIZON_M5 = 6       # M5 (แท่ง 5m): พยากรณ์ 6 แท่ง = 30 นาที
DEADZONE = 0.25      # ลดลง เพื่อให้ได้ samples มากขึ้น (option ใช้ deadzone เล็ก)
MIN_VALID_ROWS = 300  # ลดลง เพราะข้อมูลมีจำกัด
CONF_GRID = [0.50, 0.52, 0.55, 0.58, 0.60, 0.62, 0.65, 0.68, 0.70]

MODEL_VERSION = "v2_meanrev"  # version tag สำหรับ model registry


def load_price_data(fetch_days: int = 0) -> pd.DataFrame:
    """รวบรวมข้อมูล 1m จากทุกแหล่งในเครื่อง (cache + csv 90d) แล้ว optional ดึงเพิ่ม"""
    candidates = [
        DATA_DIR / "deriv_frxXAUUSD_60s.csv",
        ROOT_DIR / "deriv_frxXAUUSD_60s_90d.csv",
        DATA_DIR / "deriv_frxXAUUSD_60s_90d.csv",
    ]
    parts = []
    for p in candidates:
        if p.exists():
            df = pd.read_csv(p, index_col="datetime", parse_dates=True)
            if not df.empty:
                parts.append(df)
                print(f"[Train] รวมข้อมูลจาก {p} → {len(df)} แท่ง")

    if fetch_days > 0:
        print(f"[Train] กำลังดึงข้อมูลเพิ่มย้อนหลัง {fetch_days} วันจาก Deriv ...")
        from fetch_history_paginated import fetch_history
        df_new = fetch_history("frxXAUUSD", 60, fetch_days)
        if not df_new.empty:
            parts.append(df_new)
            out = DATA_DIR / "deriv_frxXAUUSD_60s.csv"
            df_new.to_csv(out)
            print(f"[Train] ดึงเพิ่ม {len(df_new)} แท่ง → บันทึก {out}")

    if not parts:
        raise FileNotFoundError("ไม่พบข้อมูล 1m ในเครื่องเลย ใช้ --fetch-days 60 เพื่อดึงข้อมูลก่อน")

    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    print(f"[Train] รวมทั้งหมด {len(df)} แท่ง | {df.index[0]} → {df.index[-1]}")
    return df


def resample_to(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    rule = f"{minutes}min"
    o = df["open"].resample(rule, closed="left", label="left", origin="epoch").first()
    h = df["high"].resample(rule, closed="left", label="left", origin="epoch").max()
    l = df["low"].resample(rule, closed="left", label="left", origin="epoch").min()
    c = df["close"].resample(rule, closed="left", label="left", origin="epoch").last()
    v = df["volume"].resample(rule, closed="left", label="left", origin="epoch").sum()
    out = pd.concat([o, h, l, c, v], axis=1)
    out.columns = ["open", "high", "low", "close", "volume"]
    return out.dropna()


def train_one(df: pd.DataFrame, horizon: int, out_name: str, label: str):
    print(f"\n=== เทรน {label} (horizon={horizon}) → {out_name} ===")
    X, y = build_dataset_v2(df, horizon=horizon, deadzone_atr_mult=DEADZONE,
                            feature_columns=FEATURE_COLUMNS_V2)
    if len(X) < MIN_VALID_ROWS or y.nunique() < 2:
        print(f"❌ ข้อมูลไม่พอ ({len(X)} แถว, {y.nunique()} class) — ข้ามไป "
              f"ควรมีข้อมูล 1m อย่างน้อย ~{(MIN_VALID_ROWS * 5):,} แท่ง")
        return False

    X_tr, y_tr, X_val, y_val, X_test, y_test = three_way_split(X, y)
    model = make_and_fit(X_tr, y_tr, X_val, y_val)

    proba_val = model.predict_proba(X_val)[:, 1]
    proba_test = model.predict_proba(X_test)[:, 1]
    auc_val = roc_auc_score(y_val, proba_val)
    auc_test = roc_auc_score(y_test, proba_test)

    min_signals = max(20, int(len(X_val) * 0.03))
    chosen = pick_best_threshold(y_val, proba_val, min_signals)
    dynamic_conf = chosen["conf"] if chosen["conf"] is not None else 0.52
    test_eval = evaluate_on_test(y_test, proba_test, dynamic_conf, min_signals)

    print(f"  n_rows={len(X)}  auc_val={auc_val:.4f}  auc_test={auc_test:.4f}")
    print(f"  chosen_conf={dynamic_conf}  TEST winrate={test_eval['winrate']}% (n={test_eval['n']})")
    if auc_test < 0.54:
        print("  ⚠️ AUC test < 0.54 = ยังไม่แน่นอน ควรเพิ่มข้อมูลก่อนใช้เทรดจริง")

    joblib.dump({
        "model": model,
        "features": FEATURE_COLUMNS_V2,
        "horizon": horizon,
        "deadzone_atr_mult": DEADZONE,
        "chosen_conf": dynamic_conf,
        "auc_val": round(auc_val, 4),
        "auc_test": round(auc_test, 4),
        "n_rows": len(X),
        "version": MODEL_VERSION,
        "feature_set": "v2_meanrev",
        "conf_grid": CONF_GRID,
    }, MODEL_DIR / out_name)
    print(f"✅ บันทึก {out_name} เรียบร้อย (version={MODEL_VERSION})")
    return True


def main():
    parser = argparse.ArgumentParser(description="เทรนโมเดล live แยกตาม timeframe (M1/M5)")
    parser.add_argument("--fetch-days", type=int, default=0,
                        help="ดึงข้อมูลเพิ่มก่อนเทรน (0 = ใช้ข้อมูลที่มีในเครื่อง)")
    parser.add_argument("--retrain", action="store_true",
                        help="บังคับเทรนใหม่ (ลบโมเดลเก่าก่อน)")
    args = parser.parse_args()

    if args.retrain:
        for f in ["model_m1.joblib", "model_m5.joblib"]:
            p = MODEL_DIR / f
            if p.exists():
                p.unlink()
                print(f"🗑️ ลบ {f} เก่า")

    print("=== เทรนโมเดล production ใหม่: horizon ตรงกับเวลาถือออเดอร์ + Mean Reversion ===\n")
    raw_1m = load_price_data(fetch_days=args.fetch_days)

    ok_m1 = train_one(raw_1m, HORIZON_M1, "model_m1.joblib", "M1 (ถือ 15 นาที)")
    ok_m5 = train_one(resample_to(raw_1m, 5), HORIZON_M5, "model_m5.joblib", "M5 (ถือ 30 นาที)")

    print("\n=== สรุป ===")
    if ok_m1 and ok_m5:
        print("✅ โมเดลพร้อมใช้ — รันระบบได้เลย: python run_live.py")
    else:
        print("⚠️ มีบางโมเดลข้ามไปเพราะข้อมูลไม่พอ — รันอีกครั้งหลังมีข้อมูลเพิ่ม "
              "(python -m backend.ml_forecaster.train_live_models --fetch-days 90)")


if __name__ == "__main__":
    main()
