"""
config_search.py — ลองหลาย config (horizon x deadzone x feature_set) อย่างเป็นระบบ
โดยกันข้อมูลช่วงท้ายสุด (holdout) ไว้ไม่แตะเลยระหว่างค้นหา แล้วเช็คแค่ครั้งเดียวตอนจบ

ทำไมต้องกัน holdout แยกจาก walk-forward:
  - เราจะลองหลาย config พร้อมกัน (12 configs = horizon 4 แบบ x feature_set 3 แบบ)
    ถ้าเลือก "ตัวที่ดีที่สุด" จากผลบนข้อมูลชุดเดียวกับที่ใช้ทดสอบทุกตัว
    ตัวเลขของ config ที่ชนะจะสวยเกินจริงเสมอ (multiple-comparison bias — ยิ่งลองเยอะ
    ยิ่งมีโอกาสเจอตัวที่ "โชคดี" บน noise ไม่ใช่เพราะมันดีจริง)
  - ทางแก้: แบ่งข้อมูลเป็น 2 ส่วนตามเวลา
      1) search set (ข้อมูลเก่ากว่า)  → ใช้ walk-forward ลองทุก config หา "ตัวที่ดีที่สุด"
      2) holdout set (--holdout-days ท้ายสุด) → ไม่ถูกแตะเลยระหว่างค้นหา
    พอเลือก config ที่ดีที่สุดจาก search set แล้ว เทรนโมเดลตัวสุดท้ายบน search set
    ทั้งหมด (เลือก threshold จากท้าย search set เป็น val) แล้วทดสอบบน holdout
    "ครั้งเดียว" เท่านั้น — ตัวเลขจาก holdout นี้คือค่าที่เชื่อถือได้ใกล้เคียงการใช้งาน
    จริงที่สุด เพราะไม่เคยถูกใช้เลือกอะไรมาก่อนเลย

เกณฑ์เลือก config ที่ดีที่สุดจาก search set: ไม่ใช้ pooled winrate ตรงๆ (จุดเดียวหลอกได้ง่าย)
แต่ใช้ "ขอบล่างของ 95% CI ลบ breakeven" (conservative) และต้องมี n_signals ขั้นต่ำ
พอจะเชื่อถือได้ก่อน (กัน config ที่ยิงสัญญาณน้อยมากแต่ดันได้ winrate สูงจากความบังเอิญ)

รัน:
    python -m backend.ml_forecaster.config_search --holdout-days 14 --folds 6 --payout 0.82
"""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from backend.ml_forecaster.features import build_dataset as build_dataset_v1, FEATURE_COLUMNS as FEATURES_V1
from backend.ml_forecaster.features_v2 import (
    build_dataset_v2, FEATURE_COLUMNS_V2, FEATURE_COLUMNS_V2_FULL,
)
from backend.ml_forecaster.features_v3 import (
    build_dataset_v3, FEATURE_COLUMNS_PA, FEATURE_COLUMNS_PA_FULL,
)
from backend.ml_forecaster.features_v4 import (
    build_dataset_v4, FEATURE_COLUMNS_REGIME, FEATURE_COLUMNS_REGIME_FULL,
)
from backend.ml_forecaster.train_walkforward import (
    HAS_LGB, load_price_data, make_and_fit, pick_best_threshold, walkforward_eval, wilson_ci,
)

warnings.filterwarnings("ignore")

CANDIDATE_HORIZONS = [
    {"horizon": 5, "deadzone": 0.3},
    {"horizon": 3, "deadzone": 0.6},
    {"horizon": 5, "deadzone": 0.0},
    {"horizon": 15, "deadzone": 0.3},
]
FEATURE_SETS = ["v1", "v2", "v2_full", "pa", "pa_full", "regime", "regime_full"]
MIN_SIGNALS_TO_TRUST = 200  # ต่ำกว่านี้ไม่เอามาเทียบเลือก config เพราะ noise สูงเกินไป


def build_xy(raw_df: pd.DataFrame, horizon: int, deadzone: float, feature_set: str):
    if feature_set == "v1":
        return build_dataset_v1(raw_df, horizon=horizon, deadzone_atr_mult=deadzone)
    if feature_set == "v2":
        return build_dataset_v2(raw_df, horizon=horizon, deadzone_atr_mult=deadzone,
                                 feature_columns=FEATURE_COLUMNS_V2)
    if feature_set == "v2_full":
        return build_dataset_v2(raw_df, horizon=horizon, deadzone_atr_mult=deadzone,
                                 feature_columns=FEATURE_COLUMNS_V2_FULL)
    if feature_set == "pa":
        return build_dataset_v3(raw_df, horizon=horizon, deadzone_atr_mult=deadzone,
                                 feature_columns=FEATURE_COLUMNS_PA)
    if feature_set == "pa_full":
        return build_dataset_v3(raw_df, horizon=horizon, deadzone_atr_mult=deadzone,
                                 feature_columns=FEATURE_COLUMNS_PA_FULL)
    if feature_set == "regime":
        return build_dataset_v4(raw_df, horizon=horizon, deadzone_atr_mult=deadzone,
                                 feature_columns=FEATURE_COLUMNS_REGIME)
    if feature_set == "regime_full":
        return build_dataset_v4(raw_df, horizon=horizon, deadzone_atr_mult=deadzone,
                                 feature_columns=FEATURE_COLUMNS_REGIME_FULL)
    raise ValueError(f"unknown feature_set: {feature_set}")


def split_search_holdout(raw_df: pd.DataFrame, holdout_days: int):
    cutoff = raw_df.index[-1] - pd.Timedelta(days=holdout_days)
    search_df = raw_df[raw_df.index <= cutoff]
    holdout_df = raw_df  # เก็บ raw เต็ม ไปตัด X/y ด้วย cutoff อีกทีตอน build (กัน warm-up ขาด)
    return search_df, holdout_df, cutoff


def final_holdout_check(raw_df: pd.DataFrame, cutoff: pd.Timestamp, horizon: int,
                         deadzone: float, feature_set: str, payout: float):
    """เทรนโมเดลตัวสุดท้ายบนข้อมูลทั้งหมดก่อน cutoff (เผื่อ val ท้ายสุดไว้เลือก threshold)
    แล้วทดสอบบนข้อมูลหลัง cutoff (holdout) ครั้งเดียว — ไม่มีการเลือก config ใดๆ ตรงนี้แล้ว
    """
    X, y = build_xy(raw_df, horizon, deadzone, feature_set)
    is_search = X.index <= cutoff
    X_search, y_search = X[is_search], y[is_search]
    X_holdout, y_holdout = X[~is_search], y[~is_search]

    if len(X_search) < 500 or len(X_holdout) < 50 or y_search.nunique() < 2:
        return None

    val_cut = int(len(X_search) * 0.85)
    X_tr, y_tr = X_search.iloc[:val_cut], y_search.iloc[:val_cut]
    X_val, y_val = X_search.iloc[val_cut:], y_search.iloc[val_cut:]

    model = make_and_fit(X_tr, y_tr, X_val, y_val)
    proba_val = model.predict_proba(X_val)[:, 1]
    min_signals = max(10, int(len(X_val) * 0.03))
    chosen = pick_best_threshold(y_val, proba_val, min_signals)
    if chosen["conf"] is None:
        return {"n": 0}

    proba_holdout = model.predict_proba(X_holdout)[:, 1]
    conf = chosen["conf"]
    mask = (proba_holdout >= conf) | (proba_holdout <= (1 - conf))
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "conf_used": conf}

    pred = np.where(proba_holdout[mask] >= conf, 1, 0)
    wins = int((pred == y_holdout.values[mask]).sum())
    winrate = 100 * wins / n
    ci_low, ci_high = wilson_ci(wins, n)
    breakeven = 1 / (1 + payout) * 100
    return {
        "n": n, "wins": wins, "losses": n - wins, "winrate": winrate,
        "ci_low": ci_low, "ci_high": ci_high, "conf_used": conf, "breakeven": breakeven,
        "period": f"{X_holdout.index[0]:%Y-%m-%d} → {X_holdout.index[-1]:%Y-%m-%d}",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout-days", type=int, default=14,
                         help="จำนวนวันท้ายสุดที่กันไว้ ไม่ใช้เลยระหว่างค้นหา config")
    parser.add_argument("--payout", type=float, default=0.82)
    parser.add_argument("--folds", type=int, default=6,
                         help="จำนวน walk-forward fold บน search set (ไม่รวม holdout)")
    args = parser.parse_args()

    raw_df = load_price_data()
    n_days = len(raw_df) / (24 * 60)
    print(f"[Search] ข้อมูลทั้งหมด: {len(raw_df)} แท่ง (≈{n_days:.1f} วัน)")
    search_df, _, cutoff = split_search_holdout(raw_df, args.holdout_days)
    n_search_days = len(search_df) / (24 * 60)
    print(f"[Search] แบ่งเป็น search set ≈{n_search_days:.1f} วัน (ใช้ค้นหา config) + "
          f"holdout ≈{args.holdout_days} วันท้ายสุด (ไม่แตะจนกว่าจะเลือก config เสร็จ)")
    print(f"[Search] payout={args.payout}  breakeven={1/(1+args.payout)*100:.1f}%  "
          f"model={'LightGBM' if HAS_LGB else 'sklearn-fallback'}\n")

    rows = []
    for cfg in CANDIDATE_HORIZONS:
        for fset in FEATURE_SETS:
            X, y = build_xy(search_df, cfg["horizon"], cfg["deadzone"], fset)
            if len(X) < 500 or y.nunique() < 2:
                continue
            result = walkforward_eval(X, y, args.folds)
            n_total = result["n_total"]
            label = f"h={cfg['horizon']}m dz={cfg['deadzone']} feat={fset}"
            if n_total < MIN_SIGNALS_TO_TRUST:
                print(f"[Search] {label:35s} → n={n_total} (ต่ำกว่า {MIN_SIGNALS_TO_TRUST} ข้าม ไม่พอเชื่อ)")
                continue
            breakeven = 1 / (1 + args.payout) * 100
            margin = result["ci_low"] - breakeven
            print(f"[Search] {label:35s} → n={n_total:5d}  winrate={result['pooled_winrate']:.1f}%  "
                  f"CI=[{result['ci_low']:.1f},{result['ci_high']:.1f}]  margin_vs_breakeven={margin:+.1f}pp")
            rows.append({
                "horizon": cfg["horizon"], "deadzone": cfg["deadzone"], "feature_set": fset,
                "n_total": n_total, "pooled_winrate": result["pooled_winrate"],
                "ci_low": result["ci_low"], "ci_high": result["ci_high"], "margin": margin,
            })

    if not rows:
        print("\n[Search] ไม่มี config ไหนมีสัญญาณพอจะเชื่อถือได้เลย (n < "
              f"{MIN_SIGNALS_TO_TRUST} ทุกตัว) — search set อาจสั้นไป ลอง backfill เพิ่ม")
        return

    df_rank = pd.DataFrame(rows).sort_values("margin", ascending=False).reset_index(drop=True)
    print(f"\n{'=' * 90}\nอันดับ config จาก search set เรียงตาม margin เหนือ breakeven (ขอบล่าง CI):")
    print(df_rank.to_string(index=False))

    best = df_rank.iloc[0]
    print(f"\n[Search] config อันดับ 1: horizon={best['horizon']}m deadzone={best['deadzone']} "
          f"feature_set={best['feature_set']}  (margin={best['margin']:+.1f}pp บน search set)")
    if best["margin"] < 0:
        print("[Search] ⚠️ แม้แต่ตัวที่ดีที่สุดก็ยังไม่เคลียร์ breakeven บน search set เอง — "
              "การเช็ค holdout ด้านล่างแทบจะเป็นแค่ยืนยันซ้ำว่ายังไม่ผ่าน ไม่ใช่ความหวังว่าจะพลิกกลับมาดี")

    print(f"\n{'=' * 90}\nเช็ค holdout ({args.holdout_days} วันท้ายสุด, ไม่เคยถูกใช้เลือก config เลย) "
          f"ด้วย config ที่เลือกมา — ครั้งเดียวเท่านั้น:\n")
    hc = final_holdout_check(raw_df, cutoff, int(best["horizon"]), float(best["deadzone"]),
                              best["feature_set"], args.payout)
    if hc is None or hc["n"] == 0:
        print("[Holdout] ไม่มีสัญญาณเกิดขึ้นใน holdout เลย (หรือข้อมูลไม่พอ) — สรุปไม่ได้จากรอบนี้")
        return

    print(f"ช่วง holdout: {hc['period']}  |  conf ที่ใช้: {hc['conf_used']}")
    print(f"n={hc['n']}  wins={hc['wins']}  losses={hc['losses']}  winrate={hc['winrate']:.1f}%")
    print(f"95% CI: [{hc['ci_low']:.1f}%, {hc['ci_high']:.1f}%]   breakeven={hc['breakeven']:.1f}%")
    if hc["ci_high"] < hc["breakeven"]:
        print("❌ Holdout ยืนยันว่ายังไม่ถึง breakeven — อย่าเพิ่งเอา config นี้ไปใช้เงินจริง")
    elif hc["ci_low"] > hc["breakeven"]:
        print("✅ Holdout ผ่าน breakeven ด้วย (นี่คือหลักฐานที่หนักแน่นกว่าตอน search set มาก "
              "เพราะไม่เคยถูกใช้เลือกอะไรมาก่อน) — ยังควรเฝ้าดู live paper-trade ต่ออีกระยะก่อนใช้เงินจริงอยู่ดี")
    else:
        print("⚠️ Holdout อยู่ในโซนก้ำกึ่งเหมือนเดิม — ต้องการข้อมูล/ระยะเวลาสังเกตเพิ่มก่อนสรุป")


if __name__ == "__main__":
    main()
