"""
hybrid_train.py — เทรน ML แบบ Hybrid: Rule-Based Setup (ที่มี edge อยู่แล้ว)
เป็น feature + เป็น "ประตูกรอง" เพื่อให้ ML ต่อยอดให้แม่นยิ่งขึ้น
=====================================================================================
แนวคิด:
  - Rule-Based V4 (setup_scorer) มี edge จริง (backtest 122 วัน → 59.3% winrate)
  - ปัญหา ML เดี่ยว: feature เป็น indicator ล้วนๆ proba หดใกล้ 0.5 (max ~0.57)
    เลยขึ้น threshold 0.70 ไม่ได้
  - วิธี Hybrid: ป้อนผลตรวจของ Rule-Based (score, tier, direction, 11 ค่า frac)
    เข้าไปเป็น feature เพิ่ม → โมเดลเรียนรู้ "เมื่อ setup บอกแบบนี้ + ตลาดเป็นแบบนี้
    โอกาสชนะเท่าไหร่" แล้วใช้ confidence เป็นตัวกรองชั้นสอง

วิธีเทรน (กัน lookahead bias):
  1. เดินทีละแท่งคำนวณ Rule-Based setup (window 220) → เก็บ features
  2. label = WIN/LOSE แบบ profit-aware (ขยับ > 0.25x ATR ตามทิศ setup)
  3. Walk-forward: เทรน fold k → ยิงบนข้อมูล fold ถัดไปที่โมเดลไม่เคยเห็น
  4. เทียบผล: (a) Rule-Based ล้วน (b) Hybrid = Rule-Based FIRE/WATCH + ML conf ≥ T

รัน:
    ./venv/Scripts/python.exe -m backend.ml_forecaster.hybrid_train \
        --csv data/deriv_frxXAUUSD_300s_120d.csv --tf M5 --horizon 6 --kfold 5
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

from backend.ml_forecaster.features_v2 import build_features_v2, FEATURE_COLUMNS_V2

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    from sklearn.ensemble import HistGradientBoostingClassifier as _HG
    HAS_LGB = False

# ── Rule-Based setup features ──
SETUP_FEATURES = [
    "score", "tier_ord", "max_score",
    "trend_ema", "adx", "rsi_zone", "rsi_div", "ema100", "bb",
    "structure", "pullback", "sr", "rejection", "sma5",
]
# feature ต่อเนื่องเสริมจาก raw OHLC (เพิ่ม discriminative power)
CONTINUOUS_FEATURES = [
    "ema200_dist_pct", "ema50_dist_pct", "rsi14", "adx14",
    "bb_width_pct", "atr_pct", "momentum_5", "session_hour_sin", "session_hour_cos",
]
DEADZONE = 0.25
CONF_GRID = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
MIN_TRAIN = 400
TIER_ORD = {"NONE": 0, "WATCH": 1, "FIRE": 2}


def _make_model():
    if HAS_LGB:
        return lgb.LGBMClassifier(
            n_estimators=400, learning_rate=0.03, num_leaves=15, max_depth=4,
            min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
        )
    return _HG(max_iter=400, learning_rate=0.03, max_depth=4,
               min_samples_leaf=40, l2_regularization=0.1, random_state=42)


def _load_and_resample(path: str, tf: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["datetime"]).set_index("datetime")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df = df[["open", "high", "low", "close", "volume"]].sort_index()
    if tf == "M1":
        return df
    rule = "5min"
    o = df["open"].resample(rule, label="left", closed="left").first()
    h = df["high"].resample(rule, label="left", closed="left").max()
    l = df["low"].resample(rule, label="left", closed="left").min()
    c = df["close"].resample(rule, label="left", closed="left").last()
    v = df["volume"].resample(rule, label="left", closed="left").sum()
    out = pd.concat([o, h, l, c, v], axis=1)
    out.columns = ["open", "high", "low", "close", "volume"]
    return out.dropna()


def _build_setup_features(df_tf: pd.DataFrame, step: int = 1):
    """เดินทีละแท่ง เรียก score_setup → คืน DataFrame ฟีเจอร์ setup + ทิศทาง + label
    ใช้ step>1 เร่งความเร็ว (กันรันช้าเกินกับชุดข้อมูลใหญ่)"""
    from backend.setup_scorer import score_setup, load_config
    load_config()

    WINDOW = 220
    MIN_BARS = 60
    rows = []
    n = len(df_tf)
    bar_sec = int((df_tf.index[1] - df_tf.index[0]).total_seconds())

    # precompute feature ต่อเนื่องแบบ rolling (กันคำนวณซ้ำทุกแท่ง)
    c = df_tf["close"]
    from backend.indicators import ema, rsi as _rsi, atr as _atr, bollinger_bands
    ema200 = ema(c, 200)
    ema50 = ema(c, 50)
    rsi14 = _rsi(c, 14)
    adx14 = _atr(df_tf, 14)  # proxy (ATR แทน ADX เฉพาะ feature ต่อเนื่อง — ADX จริงอยู่ใน checklist)
    bb_up, bb_mid, bb_low = bollinger_bands(c, 20, 2.0)
    bb_width = (bb_up - bb_low) / bb_mid * 100
    atr14 = _atr(df_tf, 14)
    hour = pd.Series(df_tf.index.hour + df_tf.index.minute / 60.0, index=df_tf.index)

    for i in range(MIN_BARS, n, step):
        window = df_tf.iloc[max(0, i - WINDOW): i + 1]
        try:
            r = score_setup(window, timeframe="M5", target_hold_minutes=30)
        except Exception:
            continue
        d = r.details
        px = float(c.iloc[i])
        row = {
            "time": df_tf.index[i],
            "direction": r.direction if r.direction else "",
            "bias": r.bias,
            "tier": r.tier,
            "entry_trigger": bool(r.entry_trigger),
            "score": float(r.score),
            "tier_ord": TIER_ORD.get(r.tier, 0),
            "max_score": float(r.max_score),
            "trend_ema": float(d.get("trend_ema", {}).get("frac", 0.0)),
            "adx": float(d.get("adx", {}).get("frac", 0.0)),
            "rsi_zone": float(d.get("rsi_zone", {}).get("frac", 0.0)),
            "rsi_div": float(d.get("rsi_div", {}).get("frac", 0.0)),
            "ema100": float(d.get("ema100", {}).get("frac", 0.0)),
            "bb": float(d.get("bb", {}).get("frac", 0.0)),
            "structure": float(d.get("structure", {}).get("frac", 0.0)),
            "pullback": float(d.get("pullback", {}).get("frac", 0.0)),
            "sr": float(d.get("sr", {}).get("frac", 0.0)),
            "rejection": float(d.get("rejection", {}).get("frac", 0.0)),
            "sma5": float(d.get("sma5", {}).get("frac", 0.0)),
            "entry": px,
            "atr": float(atr14.iloc[i]) if not np.isnan(atr14.iloc[i]) else 0.0,
            # ── ต่อเนื่อง ──
            "ema200_dist_pct": (px - float(ema200.iloc[i])) / px * 100 if not np.isnan(ema200.iloc[i]) else 0.0,
            "ema50_dist_pct": (px - float(ema50.iloc[i])) / px * 100 if not np.isnan(ema50.iloc[i]) else 0.0,
            "rsi14": float(rsi14.iloc[i]) if not np.isnan(rsi14.iloc[i]) else 50.0,
            "adx14": float(adx14.iloc[i]) if not np.isnan(adx14.iloc[i]) else 0.0,
            "bb_width_pct": float(bb_width.iloc[i]) if not np.isnan(bb_width.iloc[i]) else 0.0,
            "atr_pct": float(atr14.iloc[i]) / px * 100 if not np.isnan(atr14.iloc[i]) else 0.0,
            "momentum_5": float(c.pct_change(5).iloc[i] * 100) if i >= 5 and not np.isnan(c.pct_change(5).iloc[i]) else 0.0,
            "session_hour_sin": np.sin(2 * np.pi * hour.iloc[i] / 24),
            "session_hour_cos": np.cos(2 * np.pi * hour.iloc[i] / 24),
        }
        rows.append(row)

    sdf = pd.DataFrame(rows).set_index("time")
    if sdf.empty:
        raise RuntimeError("ไม่มีแถว setup features — ข้อมูลสั้นเกินไป?")
    return sdf


def _add_labels(sdf: pd.DataFrame, df_tf: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """label profit-aware ตามทิศทางที่ setup บอก:
    1 = ราคาเคลื่อนตามทิศ setup เกิน 0.25x ATR (ชนะจริง) 0 = ตรงข้าม NaN = ไม่มีทิศ"""
    out = sdf.copy()
    closes = df_tf["close"]
    locs = df_tf.index.get_indexer(out.index)
    labels = np.full(len(out), np.nan)
    for j, (idx, row) in enumerate(out.iterrows()):
        loc = locs[j]
        if loc + horizon >= len(closes):
            continue
        entry = float(closes.iloc[loc])
        exit_px = float(closes.iloc[loc + horizon])
        delta = exit_px - entry
        thr = max(row["atr"] * DEADZONE, 1e-9)
        if row["direction"] == "CALL":
            if delta > thr:
                labels[j] = 1
            elif delta < -thr:
                labels[j] = 0
        elif row["direction"] == "PUT":
            if delta < -thr:
                labels[j] = 1
            elif delta > thr:
                labels[j] = 0
    out["label"] = labels
    return out


def run_hybrid(sdf: pd.DataFrame, kfold: int, df_tf: pd.DataFrame, horizon: int) -> dict:
    valid = sdf["label"].notna() & sdf["direction"].ne("")
    X = sdf.loc[valid, SETUP_FEATURES + CONTINUOUS_FEATURES]
    y = sdf.loc[valid, "label"].astype(int)
    times = X.index
    n = len(X)
    print(f"  samples ใช้เทรน: {n} (มีทิศ + label)")

    fold_edges = np.linspace(0, n, kfold + 1, dtype=int)
    # fold แรกต้องมี train พอ
    if fold_edges[1] < MIN_TRAIN:
        fold_edges[1] = MIN_TRAIN
    results: dict = {c: {"n": 0, "wins": 0} for c in CONF_GRID}
    # rule-based ล้วน (เฉพาะ entry_trigger)
    rb = {"n": 0, "wins": 0}
    aucs = []
    error_memory = []  # (time, features) ของสัญญาณที่ยิงแล้วแพ้ เพื่อ feedback

    for k in range(1, kfold):
        tr_end = fold_edges[k]
        te_start = fold_edges[k]
        te_end = fold_edges[k + 1] if k + 1 < kfold else n
        if te_end - te_start < 20:
            continue

        X_tr, y_tr = X.iloc[:tr_end], y.iloc[:tr_end]
        if len(X_tr) < MIN_TRAIN or y_tr.nunique() < 2:
            print(f"  [fold {k}] เทรนไม่พอ — ข้าม")
            continue
        cut = int(len(X_tr) * 0.9)

        # feedback: ให้ตัวอย่างที่เคยยิงพลาด (ใน fold ก่อน) มีน้ำหนักสูงขึ้น
        sw = np.ones(cut)
        if error_memory:
            hit = 0
            X_cut = X_tr.iloc[:cut]
            for (ets, _) in error_memory:
                td = (X_cut.index - ets).total_seconds()
                near = (td >= 0) & (td <= 3 * int((df_tf.index[1] - df_tf.index[0]).total_seconds()))
                if near.any():
                    sw[near] *= 1.5
                    hit += 1
            if hit:
                print(f"  [fold {k}] feedback: เพิ่มน้ำหนัก {hit} ตัวอย่างที่เคยพลาด")

        model = _make_model()
        if HAS_LGB:
            model.fit(X_tr.iloc[:cut], y_tr.iloc[:cut], sample_weight=sw,
                      eval_set=[(X_tr.iloc[cut:], y_tr.iloc[cut:])],
                      callbacks=[lgb.early_stopping(30, verbose=False)])
        else:
            model.fit(X_tr.iloc[:cut], y_tr.iloc[:cut], sample_weight=sw)
        try:
            auc = roc_auc_score(y_tr.iloc[cut:], model.predict_proba(X_tr.iloc[cut:])[:, 1])
        except ValueError:
            auc = float("nan")
        aucs.append(auc)

        X_te = X.iloc[te_start:te_end]
        if X_te.empty:
            continue
        proba = model.predict_proba(X_te)[:, 1]
        y_te = y.iloc[te_start:te_end].values
        te_times = times[te_start:te_end]
        # proba คือ P(label=1) = P(ทิศ setup ถูก) → กรองเอา proba สูง

        sdf_te = sdf.loc[te_times]
        # กันสแปม: หลังยิง 1 ไม้ ต้องเว้น horizon แท่งก่อนยิงใหม่ (เหมือน live)
        bar_sec = int((df_tf.index[1] - df_tf.index[0]).total_seconds())
        last_trade_ts = None
        for j, (ts, p) in enumerate(zip(te_times, proba)):
            is_trigger = bool(sdf_te["entry_trigger"].iloc[j])
            actual_win = y_te[j]
            if last_trade_ts is not None:
                bars_since = (ts - last_trade_ts).total_seconds() / bar_sec
                if bars_since < horizon:
                    continue
            # Hybrid แท้: ยิงต่อเมื่อ RB-FIRE (entry_trigger) และ ML conf ≥ threshold
            if is_trigger:
                rb["n"] += 1
                rb["wins"] += 1 if actual_win else 0
                last_trade_ts = ts
                for c in CONF_GRID:
                    if p >= c:
                        results[c]["n"] += 1
                        results[c]["wins"] += 1 if actual_win else 0

        # เก็บ error cases (สัญญาณที่ยิงแล้วแพ้) จาก RB trigger ใน fold นี้
        for j, ts in enumerate(te_times):
            if bool(sdf_te["entry_trigger"].iloc[j]):
                if y_te[j] == 0:
                    error_memory.append((ts, X_te.iloc[j]))
        print(f"  [fold {k}] test {len(X_te)} | AUC_val={auc:.4f} | "
              f"RB-FIRE={rb['n']} | hybrid@{min(CONF_GRID)}={results[min(CONF_GRID)]['n']} "
              f"| errors_saved={len(error_memory)}")

    summary = {
        "rule_based_fire": {
            "n": rb["n"], "wins": rb["wins"],
            "winrate_pct": round(rb["wins"] / rb["n"] * 100, 2) if rb["n"] else 0.0,
            "net_units": round(rb["wins"] * 0.82 - (rb["n"] - rb["wins"]), 2) if rb["n"] else 0.0,
        },
        "hybrid": {},
        "_auc_avg": round(float(np.nanmean(aucs)), 4) if aucs else None,
    }
    for c, r in results.items():
        summary["hybrid"][c] = {
            "n": r["n"], "wins": r["wins"],
            "winrate_pct": round(r["wins"] / r["n"] * 100, 2) if r["n"] else 0.0,
            "net_units": round(r["wins"] * 0.82 - (r["n"] - r["wins"]), 2) if r["n"] else 0.0,
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Hybrid: Rule-Based setup features + ML")
    parser.add_argument("--csv", type=str, required=True)
    parser.add_argument("--tf", type=str, choices=["M1", "M5"], default="M5")
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--kfold", type=int, default=5)
    parser.add_argument("--step", type=int, default=1,
                        help="เรียก score_setup ทุกๆ N แท่ง (มาก=เร็ว แต่พลาดจังหวะสั้น)")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    df_tf = _load_and_resample(args.csv, args.tf)
    print(f"ข้อมูล {args.tf}: {len(df_tf)} แท่ง | {df_tf.index[0]} → {df_tf.index[-1]}")
    print("สร้าง setup features (เดินทีละแท่ง score_setup) ...")
    sdf = _build_setup_features(df_tf, step=args.step)
    print(f"  setup rows: {len(sdf)} | FIRE={int((sdf['tier']=='FIRE').sum())} "
          f"WATCH={int((sdf['tier']=='WATCH').sum())}")
    sdf = _add_labels(sdf, df_tf, args.horizon)
    print(f"  มี label: {int(sdf['label'].notna().sum())}")

    print(f"\n=== Hybrid walk-forward ({args.kfold} folds | horizon={args.horizon}) ===")
    summary = run_hybrid(sdf, args.kfold, df_tf, args.horizon)

    print("\n" + "=" * 80)
    print(f"  HYBRID RESULT — {args.tf} | AUC_avg={summary['_auc_avg']}")
    print("=" * 80)
    rb = summary["rule_based_fire"]
    print(f"  Rule-Based FIRE ล้วน : n={rb['n']}  WR={rb['winrate_pct']}%  "
          f"Net={rb['net_units']:+.2f}")
    print(f"  {'ML conf':>8} | {'n':>5} | {'Winrate':>8} | {'Net(0.82)':>10}")
    print("  " + "-" * 40)
    for c in CONF_GRID:
        h = summary["hybrid"][c]
        print(f"  {c:>8.2f} | {h['n']:>5} | {h['winrate_pct']:>7.2f}% | {h['net_units']:>+10.2f}")

    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        print(f"  → บันทึกที่ {args.out}")


if __name__ == "__main__":
    main()
