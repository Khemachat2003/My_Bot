"""
macro_config_search.py — v2: full grid (horizon x deadzone x {regime, regime_full} x {macro on/off})
เลือก config ที่ดีที่สุดจาก search set (margin = ci_low - breakeven) แล้วเช็ค holdout ครั้งเดียว
เหมือน pattern เดียวกับ config_search.py ทุกประการ
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd

from backend.data_feed.macro_feed import load_cached_macro
from backend.ml_forecaster.features_v4 import (
    build_features_v4, FEATURE_COLUMNS_REGIME, FEATURE_COLUMNS_REGIME_FULL,
)
from backend.ml_forecaster.features_macro import add_macro_features, macro_columns
from backend.ml_forecaster.features import make_labels
from backend.ml_forecaster.train_walkforward import (
    HAS_LGB, load_price_data, make_and_fit, pick_best_threshold, walkforward_eval, wilson_ci,
)
from backend.ml_forecaster.config_search import split_search_holdout, MIN_SIGNALS_TO_TRUST

warnings.filterwarnings("ignore")

CANDIDATE_HORIZONS = [
    {"horizon": 5, "deadzone": 0.3},
    {"horizon": 3, "deadzone": 0.6},
    {"horizon": 5, "deadzone": 0.0},
    {"horizon": 15, "deadzone": 0.3},
]
BASE_FEATURE_SETS = {
    "regime": FEATURE_COLUMNS_REGIME,
    "regime_full": FEATURE_COLUMNS_REGIME_FULL,
}


def build_xy(raw_df, macro_data, horizon, deadzone, base_cols, use_macro):
    feat_df = build_features_v4(raw_df)
    cols = list(base_cols)
    if use_macro:
        feat_df = add_macro_features(feat_df, macro_data)
        cols += macro_columns(macro_data)
    y = make_labels(feat_df, horizon=horizon, deadzone_atr_mult=deadzone)
    X = feat_df[cols]
    valid = X.notna().all(axis=1) & y.notna()
    return X[valid], y[valid]


def final_holdout_check(raw_df, macro_data, cutoff, horizon, deadzone, base_cols, use_macro, payout):
    X, y = build_xy(raw_df, macro_data, horizon, deadzone, base_cols, use_macro)
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
    parser.add_argument("--holdout-days", type=int, default=14)
    parser.add_argument("--payout", type=float, default=0.82)
    parser.add_argument("--folds", type=int, default=6)
    args = parser.parse_args()

    macro_data = load_cached_macro()
    if not macro_data:
        print("[MacroSearch] ❌ ไม่พบ macro CSV cache — รัน macro_feed ก่อน")
        return

    raw_df = load_price_data()
    search_df, _, cutoff = split_search_holdout(raw_df, args.holdout_days)
    macro_search = {name: df[df.index <= cutoff] for name, df in macro_data.items()}
    breakeven = 1 / (1 + args.payout) * 100
    print(f"[MacroSearch] payout={args.payout}  breakeven={breakeven:.1f}%  "
          f"model={'LightGBM' if HAS_LGB else 'sklearn-fallback'}\n")

    rows = []
    for cfg in CANDIDATE_HORIZONS:
        for fname, cols in BASE_FEATURE_SETS.items():
            for use_macro in [False, True]:
                X, y = build_xy(search_df, macro_search, cfg["horizon"], cfg["deadzone"], cols, use_macro)
                if len(X) < 500 or y.nunique() < 2:
                    continue
                result = walkforward_eval(X, y, args.folds)
                n_total = result["n_total"]
                label = f"h={cfg['horizon']}m dz={cfg['deadzone']} feat={fname}{'+macro' if use_macro else ''}"
                if n_total < MIN_SIGNALS_TO_TRUST:
                    print(f"[MacroSearch] {label:38s} → n={n_total} (ต่ำกว่า {MIN_SIGNALS_TO_TRUST} ข้าม)")
                    continue
                margin = result["ci_low"] - breakeven
                print(f"[MacroSearch] {label:38s} → n={n_total:5d}  winrate={result['pooled_winrate']:.1f}%  "
                      f"CI=[{result['ci_low']:.1f},{result['ci_high']:.1f}]  margin={margin:+.1f}pp")
                rows.append({**cfg, "feature_set": fname, "use_macro": use_macro,
                             "n_total": n_total, "margin": margin})

    if not rows:
        print("\n[MacroSearch] ไม่มี config ไหนสัญญาณพอเลย")
        return

    df_rank = pd.DataFrame(rows).sort_values("margin", ascending=False).reset_index(drop=True)
    print(f"\n{'=' * 90}\nอันดับ config ตาม margin:")
    print(df_rank.to_string(index=False))

    best = df_rank.iloc[0]
    print(f"\n[MacroSearch] อันดับ 1: horizon={best['horizon']}m deadzone={best['deadzone']} "
          f"feat={best['feature_set']} macro={best['use_macro']}  margin={best['margin']:+.1f}pp")

    print(f"\n{'=' * 90}\nเช็ค holdout ({args.holdout_days} วันท้ายสุด) ครั้งเดียว:\n")
    hc = final_holdout_check(raw_df, macro_data, cutoff, int(best["horizon"]), float(best["deadzone"]),
                              BASE_FEATURE_SETS[best["feature_set"]], bool(best["use_macro"]), args.payout)
    if hc is None or hc["n"] == 0:
        print("[Holdout] ไม่มีสัญญาณ หรือข้อมูลไม่พอ")
        return

    print(f"ช่วง holdout: {hc['period']}  |  conf: {hc['conf_used']}")
    print(f"n={hc['n']}  wins={hc['wins']}  losses={hc['losses']}  winrate={hc['winrate']:.1f}%")
    print(f"95% CI: [{hc['ci_low']:.1f}%, {hc['ci_high']:.1f}%]   breakeven={hc['breakeven']:.1f}%")
    if hc["ci_high"] < hc["breakeven"]:
        print("❌ Holdout ยืนยันว่ายังไม่ถึง breakeven")
    elif hc["ci_low"] > hc["breakeven"]:
        print("✅ Holdout ผ่าน breakeven — ยังควร paper-trade ต่อก่อนใช้เงินจริง")
    else:
        print("⚠️ ก้ำกึ่ง — ต้องการข้อมูล/เวลาสังเกตเพิ่ม")


if __name__ == "__main__":
    main()