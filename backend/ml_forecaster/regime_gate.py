"""
regime_gate.py — ML Regime-Gate: พยากรณ์ว่า "แตะ EMA200 อยู่ใน regime ที่ได้เปรียบหรือไม่"
==========================================================================================
โจทย์: ข้อมูล 4 เดือนแสดงว่า "แตะ EMA200" ชนะ 61.75% เฉพาะ ส.ค. แต่ 43-45% ใน เม.ย/พ.ค/ก.ค
      → การเพิ่ม features ให้ ML เดาทุกแท่งไม่มีทางถึง 60% เพราะ edge อยู่ใน "ช่วง" ไม่ใช่ "แท่ง"
      → ให้ ML ตัดสินว่า ตอนนี้เป็น regime ที่ควรยิง setup หรือไม่ (gate) ก่อนยิง FIRE

นิยาม candidate (proxy ของ FIRE):
  - อยู่ใกล้ EMA200 (dist ≤ 0.35%) และเทรน align (EMA50/100/200 เรียงทิศ)
  - label = ผล 30 นาทีถัดไปตามทิศเทรน (> 0.25 ATR — deadzone ตัดออก เหมือนระบบจริง)

Feature (ย้อนหลังเท่านั้น — ไม่มี lookahead):
  - trend strength: adx, adx slope, ema_align, mtf15 trend
  - trend quality: ema200_slope_48 (ความชัน EMA200 4 ชม.), ema200_dist, bb_pos
  - volatility regime: atr_pct, atr_rank_500/2000, atr_expanding, rvol_zscore
  - context: rsi_14, dist_vwap_pct, session

วัดผล: walk-forward (expanding) — เปรียบ baseline (ยิงทุก candidate) vs gated @threshold
GATE ผ่านเมื่อ: winrate ≥60% และ n ≥ 30 (out-of-sample) และดีกว่า baseline ชัดเจน

รัน:
    ./venv/Scripts/python.exe -m backend.ml_forecaster.regime_gate \
        --csv data/deriv_frxXAUUSD_300s_120d.csv --kfold 6
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sklearn.metrics import roc_auc_score

from backend.indicators import rsi
from backend.ml_forecaster.features_v2 import build_features_v2, SESSION_COLUMNS
from backend.ml_forecaster.features_regime import add_volatility_regime_features
from backend.ml_forecaster.train_hybrid_v3 import add_ema200_features, load_csv

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    from sklearn.ensemble import HistGradientBoostingClassifier as _HG
    HAS_LGB = False

DEADZONE = 0.25
HORIZON = 6
TOUCH_TOL = 0.35
PAYOUT = 0.82
BREAKEVEN = 1 / (1 + PAYOUT) * 100.0
MIN_TRAIN = 500          # candidate ขั้นต่ำใน train (หายาก — ไม่เหมือนทุกแท่ง)
MIN_N = 30               # สัญญาณขั้นต่ำก่อนเชื่อ winrate
GOAL = 60.0
CONF_GRID = [0.52, 0.55, 0.58, 0.60, 0.62, 0.65, 0.70]

BASE_FEATURES = [
    "adx", "adx_slope", "atr_pct", "rsi_14", "bb_pos", "dist_vwap_pct",
    "mtf15_ema_trend", "mtf15_ema_dist_pct", "mtf15_rsi",
    "ema200_dist_abs_pct", "ema200_band", "ema_align", "ema200_crossed100",
    "ema200_slope_48",
    "atr_rank_500", "atr_rank_2000", "atr_expanding", "rvol_zscore",
    "dxy_slope_24", "dxy_trend_48", "dxy_rsi", "gold_1h_slope", "gold_1h_trend",
] + SESSION_COLUMNS


def add_macro_features(feat: pd.DataFrame, macro: pd.DataFrame | None) -> pd.DataFrame:
    """รวม macro 1 ชม. (DXY + เทรนด์ 1h ของทอง) แบบ merge_asof ย้อนหลัง — ไม่มี lookahead"""
    feat = feat.copy()
    macro_cols = ["dxy_slope_24", "dxy_trend_48", "dxy_rsi", "gold_1h_slope", "gold_1h_trend"]
    for c in macro_cols:
        if c in feat.columns:
            feat = feat.drop(columns=c)
    if macro is not None and not macro.empty:
        m = macro[["close"]].copy()
        m.columns = ["dxy_close"]
        m["dxy_slope_24"] = m["dxy_close"].pct_change(24) * 100.0
        m["dxy_trend_48"] = np.sign(m["dxy_close"] - m["dxy_close"].shift(48))
        m["dxy_rsi"] = rsi(m["dxy_close"], 14)
        m = m.drop(columns=["dxy_close"])

        g = feat[["close"]].resample("1h").last().dropna()
        g["gold_1h_slope"] = g["close"].pct_change(24) * 100.0
        g["gold_1h_trend"] = np.sign(g["close"] - g["close"].rolling(24).mean())
        g = g.drop(columns=["close"])

        idx = feat.index.sort_values()
        sorted_feat = feat.loc[idx]
        for right in (m, g):
            merged = pd.merge_asof(sorted_feat, right, left_index=True, right_index=True,
                                   direction="backward")
            for c in right.columns:
                feat.loc[idx, c] = merged[c].values
    for c in macro_cols:
        if c not in feat.columns:
            feat[c] = np.nan
    return feat


def build_dataset(df_tf: pd.DataFrame, macro: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[str]]:
    feat = build_features_v2(df_tf)
    feat = add_volatility_regime_features(feat)
    feat = add_ema200_features(feat)
    feat = add_macro_features(feat, macro)

    # ── features เพิ่มเฉพาะ gate ──
    e200 = feat["close"].ewm(span=200, adjust=False).mean()
    feat["ema200_slope_48"] = (e200 - e200.shift(48)) / e200.shift(48) * 100.0
    feat["adx_slope"] = feat["adx"] - feat["adx"].shift(12)

    # ── candidate: แตะ/near EMA200 + เทรน align ──
    feat["_cand"] = ((feat["ema200_dist_abs_pct"] <= TOUCH_TOL)
                     & (feat["ema_align"] != 0)).astype(int)

    # ── label: เด้งตามทิศเทรนใน 30 นาทีถัดไป (> 0.25 ATR) ──
    future = feat["close"].shift(-HORIZON)
    delta = future - feat["close"]
    thr = feat["atr"] * DEADZONE if "atr" in feat else feat["atr_pct"] / 100.0 * feat["close"] * DEADZONE
    up_move = delta > thr
    down_move = delta < -thr
    y_up = pd.Series(np.nan, index=feat.index)
    y_up[up_move] = 1.0
    y_up[down_move] = 0.0

    # ทิศที่ถูกต้องสำหรับ candidate: align=1 → CALL (ชนะเมื่อเด้งขึ้น), align=-1 → PUT (ชนะเมื่อลง)
    # เราทำ target = P(ผลถูกตามทิศเทรน)
    target = pd.Series(np.nan, index=feat.index)
    up_align = feat["ema_align"] == 1
    target[up_align] = y_up[up_align]
    target[~up_align & (feat["ema_align"] == -1)] = 1.0 - y_up[~up_align & (feat["ema_align"] == -1)]

    feat["_target"] = target
    cols = [c for c in BASE_FEATURES if c in feat.columns]
    return feat, cols


def _make_model():
    if HAS_LGB:
        return lgb.LGBMClassifier(
            n_estimators=200, learning_rate=0.04, num_leaves=8, max_depth=3,
            min_child_samples=30, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
        )
    return _HG(max_iter=200, learning_rate=0.04, max_depth=3,
               min_samples_leaf=30, l2_regularization=0.1, random_state=42)


def run(feat: pd.DataFrame, cols: list[str], kfold: int) -> dict:
    cand = feat[feat["_cand"] == 1].dropna(subset=["_target"])
    cand = cand.dropna(subset=cols)
    n = len(cand)
    print(f"candidate (แตะ EMA200 + align): {n} แถว "
          f"| baseline winrate={cand['_target'].mean() * 100:.2f}%")

    fold_edges = np.linspace(0, n, kfold + 1, dtype=int)
    if fold_edges[1] < MIN_TRAIN:
        fold_edges[1] = MIN_TRAIN

    X_all = cand[cols]
    y_all = cand["_target"]
    results = {c: {"n": 0, "wins": 0} for c in CONF_GRID}
    base_n = base_wins = 0
    aucs = []

    for k in range(1, kfold):
        te_start, te_end = fold_edges[k], fold_edges[k + 1]
        if k + 1 >= kfold:
            te_end = n
        if te_end - te_start < 15:
            continue
        tr_idx = cand.index[:fold_edges[k]]
        X_tr = X_all.loc[X_all.index.intersection(tr_idx)]
        y_tr = y_all.loc[y_all.index.intersection(tr_idx)]
        if len(X_tr) < MIN_TRAIN or y_tr.nunique() < 2:
            print(f"  [fold {k}] เทรนไม่พอ ({len(X_tr)}) — ข้าม")
            continue

        cut = int(len(X_tr) * 0.9)
        X_val, y_val = X_tr.iloc[cut:], y_tr.iloc[cut:]
        X_tr_f, y_tr_f = X_tr.iloc[:cut], y_tr.iloc[:cut]

        model = _make_model()
        if HAS_LGB:
            model.fit(X_tr_f, y_tr_f, eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(25, verbose=False)])
        else:
            model.fit(X_tr_f, y_tr_f)
        try:
            aucs.append(roc_auc_score(y_val, model.predict_proba(X_val)[:, 1]))
        except ValueError:
            pass

        te_idx = cand.index[te_start:te_end]
        X_te = X_all.loc[X_all.index.intersection(te_idx)]
        y_te = y_all.loc[y_all.index.intersection(te_idx)]
        if X_te.empty:
            continue
        proba = model.predict_proba(X_te)[:, 1]

        base_n += len(y_te)
        base_wins += int(y_te.sum())
        for j, ts in enumerate(X_te.index):
            p = float(proba[j])
            for c in CONF_GRID:
                if p >= c:
                    results[c]["n"] += 1
                    results[c]["wins"] += 1 if bool(y_te.iloc[j]) else 0
        print(f"  [fold {k}] test {len(X_te)} candidate | AUC_val={aucs[-1] if aucs else float('nan'):.4f} "
              f"| baseline={y_te.mean() * 100:.1f}% | gated@{CONF_GRID[3]}={results[CONF_GRID[3]]['n']} ไม้")

    summary = {"_baseline": {
        "n": base_n, "winrate_pct": round(base_wins / base_n * 100, 2) if base_n else None,
    }}
    for c, r in results.items():
        nn, w = r["n"], r["wins"]
        wr = w / nn * 100 if nn else 0.0
        net = w * PAYOUT - (nn - w) if nn else 0.0
        summary[c] = {"n": nn, "wins": w, "winrate_pct": round(wr, 2),
                      "net_units": round(net, 2)}
    summary["_auc_avg"] = round(float(np.nanmean(aucs)), 4) if aucs else None

    # feature importance สุดท้าย (fit บนข้อมูลทั้งหมด) — ตรวจกลไก/กัน fluke
    if len(cand) >= MIN_TRAIN and len(cand.columns):
        m = _make_model()
        m.fit(X_all, y_all)
        if hasattr(m, "feature_importances_"):
            imp = pd.Series(m.feature_importances_, index=cols).sort_values(ascending=False)
            summary["_importance_top10"] = imp.head(10).round(3).to_dict()
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=str, required=True)
    ap.add_argument("--macro", type=str, default=None)
    ap.add_argument("--kfold", type=int, default=6)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    df_tf = load_csv(args.csv)
    macro = load_csv(args.macro) if args.macro else None
    feat, cols = build_dataset(df_tf, macro)
    print(f"ข้อมูล: {len(df_tf)} แท่ง M5 | {df_tf.index[0]} → {df_tf.index[-1]} | features={len(cols)}" +
          (" | +macro" if macro is not None else ""))

    s = run(feat, cols, args.kfold)

    print("\n" + "=" * 72)
    print(f"  REGIME-GATE RESULT | AUC_avg={s['_auc_avg']} | baseline={s['_baseline']}")
    print("=" * 72)
    print(f"  {'Conf':>6} | {'n':>5} | {'Winrate':>8} | {'Net(0.82)':>10} | Breakeven {BREAKEVEN:.2f}%")
    print("  " + "-" * 58)
    gate_hit = False
    for c in CONF_GRID:
        r = s[c]
        ok = "✅" if (r["n"] >= MIN_N and r["winrate_pct"] >= GOAL
                      and r["winrate_pct"] > s["_baseline"]["winrate_pct"]) else ""
        if ok:
            gate_hit = True
        print(f"  {c:>6.2f} | {r['n']:>5} | {r['winrate_pct']:>7.2f}% | "
              f"{r['net_units']:>+10.2f} {ok}")

    print("\n  GATE (≥60%, n≥30, ดีกว่า baseline): " +
          ("✅ ผ่าน — ML ระบุ regime ได้จริง" if gate_hit else "⛔ ยังไม่ถึง"))
    if s.get("_importance_top10"):
        print("\n  Top-10 feature importance (fit ทั้งชุด):")
        for k, v in s["_importance_top10"].items():
            print(f"    {k:<22} {v:.3f}")
    if args.out:
        Path(args.out).write_text(json.dumps(
            {"kfold": args.kfold, "n_features": len(cols), "summary": s},
            indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  บันทึกที่ {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
