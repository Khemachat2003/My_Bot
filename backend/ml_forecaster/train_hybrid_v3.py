"""
train_hybrid_v3.py — ทดลองโมเดลใหม่: features EMA200 + setup context + feedback
====================================================================================
เป้าหมาย: ทำให้ ML ชนะ ≥60% (binary payout 0.82 → breakeven 54.95%) ก่อนแตะระบบจริง

เพิ่มจาก feedback_train/auto_retrain:
  1. features กลุ่ม EMA200 (หลักฐานจาก backfill: band 0.10-0.35% = 75% ชนะ)
     - ema200_dist_pct / dist_abs / near / band / crossed100 / ema_align
  2. features บริบท setup (st_* 10 checklist + score/direction/tier) merge_asof จาก DB
  3. เรียนรู้จากสัญญาณจริง (--real-json): นำ ml_signals ที่ WIN/LOSE จริงใส่เป็นแถว
     เทรนตรง ๆ (label ตามผลจริง) เฉพาะ fold ที่ผลรู้แล้ว (กัน lookahead)

วัดผล: walk-forward (expanding window) out-of-sample — winrate@threshold + net(0.82) + AUC
Gate: ชนะ ≥60% และ n ≥ MIN_N ถึงจะแนะนำทับโมเดล production ได้

รัน (venv ของ dev เครื่อง Windows):
    ./venv/Scripts/python.exe -m backend.ml_forecaster.train_hybrid_v3 \
        --csv data/deriv_frxXAUUSD_300s_120d.csv --feat hybrid --kfold 6
    ./venv/Scripts/python.exe -m backend.ml_forecaster.train_hybrid_v3 \
        --csv data/deriv_frxXAUUSD_300s_120d.csv --feat v2   (เทียบ baseline)

    # บวกสัญญาณจริง (dump จาก /api/ml/signals):
    ./venv/Scripts/python.exe -m backend.ml_forecaster.train_hybrid_v3 \
        --csv data/deriv_frxXAUUSD_300s_120d.csv --feat hybrid \
        --real-json data/ml_real_signals.json
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

from backend.ml_forecaster.features_v2 import FEATURE_COLUMNS_V2, build_features_v2
from backend.ml_forecaster.features import make_labels

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    from sklearn.ensemble import HistGradientBoostingClassifier as _HG
    HAS_LGB = False

DEADZONE = 0.25
CONF_GRID = [0.55, 0.58, 0.60, 0.62, 0.65, 0.70, 0.75, 0.80]
PAYOUT = 0.82
BREAKEVEN = 1 / (1 + PAYOUT) * 100.0     # 54.95%
MIN_TRAIN = 1500
MIN_N = 30                                # สัญญาณขั้นต่ำก่อนสรุป winrate
GOAL_WINRATE = 60.0
REAL_WEIGHT = 3.0                         # น้ำหนักของแถวสัญญาณจริง (เรียนรู้ผลจริง)
EMA200_NR_TOL = 0.35                      # dist200 ≤ 0.35% = near (ตรงกับ setup_scorer)

# ── EMA200 feature block ──────────────────────────────────────────────────

def add_ema200_features(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    e50 = c.ewm(span=50, adjust=False).mean()
    e100 = c.ewm(span=100, adjust=False).mean()
    e200 = c.ewm(span=200, adjust=False).mean()
    out = df.copy()
    out["ema200_dist_pct"] = (c - e200) / e200 * 100.0              # signed (+ = เหนือเส้น)
    out["ema200_dist_abs_pct"] = (c - e200).abs() / e200 * 100.0
    out["ema200_near"] = (out["ema200_dist_abs_pct"] <= EMA200_NR_TOL).astype(int)
    out["ema200_band"] = np.select(
        [out["ema200_dist_abs_pct"] < 0.10, out["ema200_dist_abs_pct"] <= EMA200_NR_TOL],
        [2.0, 1.0], default=0.0)          # 2 = แตะแน่น, 1 = near(0.10-0.35), 0 = ห่าง
    crossed = np.sign(c - e100)
    out["ema200_crossed100"] = (crossed != crossed.shift(1)).astype(int)
    align_up = (e50 > e100) & (e100 > e200)
    align_down = (e50 < e100) & (e100 < e200)
    out["ema_align"] = align_up.astype(int) - align_down.astype(int)
    return out


EMA200_FEATURES = [
    "ema200_dist_pct", "ema200_dist_abs_pct", "ema200_near", "ema200_band",
    "ema200_crossed100", "ema_align",
]


def load_setup_context(db_path: Path) -> pd.DataFrame:
    """ดึง setup_scores จาก DB → flatten เป็น st_* คอลัมน์, index = bar time"""
    if not db_path.exists():
        return pd.DataFrame()
    import sqlite3
    from backend.ml_forecaster.setup_features import (
        SETUP_FEATURE_COLUMNS, flatten_setup_dict,
    )
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT timeframe, ts, details_json, score, max_score, direction, tier,
                      entry_trigger
               FROM setup_scores ORDER BY ts""").fetchall()
    except sqlite3.Error:
        con.close()
        return pd.DataFrame()
    con.close()
    if not rows:
        return pd.DataFrame()
    recs = []
    for r in rows:
        rec = flatten_setup_dict({
            "details": json.loads(r["details_json"]) if r["details_json"] else {},
            "score": r["score"], "max_score": r["max_score"],
            "direction": r["direction"], "tier": r["tier"],
            "entry_trigger": r["entry_trigger"],
        })
        rec["ts"] = pd.to_datetime(r["ts"], utc=True)
        recs.append(rec)
    df = pd.DataFrame(recs).set_index("ts").sort_index()
    return df[[c for c in SETUP_FEATURE_COLUMNS if c in df.columns]]


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["datetime"]).set_index("datetime")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def load_real_signals(path: str) -> list[dict]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for r in rows:
        if r.get("result") not in ("WIN", "LOSE"):
            continue
        ts = pd.to_datetime(r.get("signal_time"), utc=True)
        d = (r.get("direction") or "").upper()
        if d not in ("CALL", "PUT"):
            continue
        out.append({"ts": ts, "direction": d, "result": r["result"]})
    out.sort(key=lambda x: x["ts"])
    return out


def _real_label(direction: str, result: str) -> float:
    """แมปผลจริงให้ตรง target ของโมเดล (y=1 = เด้งขึ้น):
    CALL-WIN / PUT-LOSE → 1 ; CALL-LOSE / PUT-WIN → 0"""
    win = result == "WIN"
    return 1.0 if (direction == "CALL") == win else 0.0


def _make_model():
    if HAS_LGB:
        return lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.03, num_leaves=15, max_depth=4,
            min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
        )
    return _HG(max_iter=300, learning_rate=0.03, max_depth=4,
               min_samples_leaf=50, l2_regularization=0.1, random_state=42)


def _fit_with_weights(X, y, sample_weight=None, X_val=None, y_val=None):
    m = _make_model()
    if HAS_LGB:
        m.fit(X, y, sample_weight=sample_weight,
              eval_set=[(X_val, y_val)] if X_val is not None and y_val is not None else None,
              callbacks=[lgb.early_stopping(30, verbose=False)] if X_val is not None else None)
    else:
        m.fit(X, y, sample_weight=sample_weight)
    return m


def _trade_outcome(row_ts, direction, df_tf, hold_bars):
    loc = df_tf.index.get_indexer([row_ts], method="nearest")[0]
    entry = float(df_tf["close"].iloc[loc])
    exit_i = loc + hold_bars
    if exit_i >= len(df_tf):
        return None
    exit_px = float(df_tf["close"].iloc[exit_i])
    win = (exit_px > entry) if direction == "CALL" else (exit_px < entry)
    return {"entry": entry, "exit": exit_px, "result": "WIN" if win else "LOSE"}


def build_experiment(df_tf: pd.DataFrame, feat_mode: str, db_path: Path):
    """สร้าง feature matrix + label (ทั้งชุด) แล้วคืน X_full, y_full, cols"""
    feat = build_features_v2(df_tf)
    feat = add_ema200_features(feat)
    y = make_labels(feat, horizon=6, deadzone_atr_mult=DEADZONE)

    cols = list(FEATURE_COLUMNS_V2)
    if feat_mode in ("ema200", "hybrid"):
        cols += EMA200_FEATURES
    if feat_mode == "hybrid":
        ctx = load_setup_context(db_path)
        if not ctx.empty and len(feat):
            feat = pd.merge_asof(
                feat.sort_index(), ctx.sort_index(),
                left_index=True, right_index=True, direction="backward",
                tolerance=pd.Timedelta(minutes=6),
            )
            ctx_cols = [c for c in ctx.columns if c in feat.columns]
            for c in ctx_cols:
                feat[c] = feat[c].fillna(0.0)
            cols += ctx_cols
    cols = [c for c in cols if c in feat.columns]

    X = feat[cols]
    valid = X.notna().all(axis=1) & y.notna()
    return X[valid], y[valid], cols


def run(feat: pd.DataFrame, X_full, y_full, cols, df_tf, kfold: int,
        real: list[dict], feedback: bool) -> dict:
    n = len(feat)
    fold_edges = np.linspace(0, n, kfold + 1, dtype=int)
    if fold_edges[1] < MIN_TRAIN:
        fold_edges[1] = MIN_TRAIN

    results = {c: {"n": 0, "wins": 0} for c in CONF_GRID}
    aucs = []
    error_memory: list[pd.Timestamp] = []
    real_rows = []
    bar_sec = (feat.index[1] - feat.index[0]).total_seconds()

    for k in range(1, kfold):
        tr_end, te_start, te_end = fold_edges[k], fold_edges[k], fold_edges[k + 1]
        if k + 1 >= kfold:
            te_end = n
        if te_end - te_start < 20:
            continue

        tr_idx = feat.index[:tr_end]
        X_tr = X_full.loc[X_full.index.intersection(tr_idx)]
        y_tr = y_full.loc[y_full.index.intersection(tr_idx)]
        if len(X_tr) < MIN_TRAIN or y_tr.nunique() < 2:
            print(f"  [fold {k}] เทรนไม่พอ ({len(X_tr)}) — ข้าม")
            continue

        cut = int(len(X_tr) * 0.9)
        X_val, y_val = X_tr.iloc[cut:], y_tr.iloc[cut:]
        X_tr_f, y_tr_f = X_tr.iloc[:cut], y_tr.iloc[:cut]
        sw = np.ones(len(X_tr_f))

        if feedback:
            hit = 0
            for ts in error_memory:
                near = ((X_tr_f.index - ts).total_seconds() >= 0) & \
                        ((X_tr_f.index - ts).total_seconds() <= 3 * bar_sec)
                if near.any():
                    sw[near.values] *= 1.5
                    hit += 1
            if hit:
                print(f"  [fold {k}] weight feedback อดีตพลาด: {hit} ตัวอย่าง")

        # ── ใส่สัญญาณจริง (ผลรู้แล้ว) เป็นแถวเทรน ──
        te_ts = feat.index[te_start]
        X_aug, y_aug, sw_aug = X_tr_f, y_tr_f, sw
        added = 0
        for r in real:
            if r["ts"] >= te_ts:
                continue                      # ยังไม่รู้ผลใน fold นี้ (กัน lookahead)
            loc = feat.index.get_indexer([r["ts"]], method="nearest")[0]
            if abs((feat.index[loc] - r["ts"]).total_seconds()) > 3 * bar_sec:
                continue                      # ไม่มีแท่งราคาใกล้เคียง
            row = X_full.loc[[feat.index[loc]]]
            if row.empty or row.isna().any(axis=1).any():
                continue
            X_aug = pd.concat([X_aug, row])
            y_aug = pd.concat([y_aug, pd.Series([_real_label(r["direction"], r["result"])],
                                                index=row.index)])
            sw_aug = np.append(sw_aug, REAL_WEIGHT)
            added += 1
        if added:
            print(f"  [fold {k}] ใส่สัญญาณจริงเป็นแถวเทรน: {added} (ผลจริง WIN/LOSE)")

        model = _fit_with_weights(X_aug, y_aug, sw_aug, X_val, y_val)
        try:
            aucs.append(roc_auc_score(y_val, model.predict_proba(X_val)[:, 1]))
        except ValueError:
            pass

        te_idx = feat.index[te_start:te_end]
        X_te = X_full.loc[X_full.index.intersection(te_idx)]
        if X_te.empty:
            continue
        proba = model.predict_proba(X_te)[:, 1]
        last_trade_ts = None
        fold_lose_times = []
        for j, ts in enumerate(X_te.index):
            pu, pd_ = float(proba[j]), 1.0 - float(proba[j])
            best = max(pu, pd_)
            if best < min(CONF_GRID):
                continue
            if last_trade_ts is not None:
                if (ts - last_trade_ts).total_seconds() / bar_sec < 6:
                    continue
            direction = "CALL" if pu >= pd_ else "PUT"
            for c in CONF_GRID:
                if best >= c:
                    out = _trade_outcome(ts, direction, df_tf, 6)
                    if out is not None:
                        results[c]["n"] += 1
                        results[c]["wins"] += 1 if out["result"] == "WIN" else 0
            last_trade_ts = ts
            if feedback and best >= 0.70:
                out = _trade_outcome(ts, direction, df_tf, 6)
                if out and out["result"] == "LOSE":
                    fold_lose_times.append(ts)
        error_memory.extend(fold_lose_times)
        print(f"  [fold {k}] test {len(X_te)} แถว | AUC_val={aucs[-1] if aucs else float('nan'):.4f} "
              f"| ยิง@{min(CONF_GRID)}={results[min(CONF_GRID)]['n']} ไม้ "
              f"| ลองพลาด@{0.70}เก็บ feedback={len(fold_lose_times)}")

    summary = {}
    for c, r in results.items():
        n = r["n"]
        wr = r["wins"] / n * 100 if n else 0.0
        net = r["wins"] * PAYOUT - (n - r["wins"]) if n else 0.0
        summary[c] = {
            "n": n, "wins": r["wins"], "winrate_pct": round(wr, 2),
            "net_units": round(net, 2), "breakeven": round(BREAKEVEN, 2),
        }
    summary["_auc_avg"] = round(float(np.nanmean(aucs)), 4) if aucs else None
    summary["_n_folds"] = kfold - 1
    return {"summary": summary}


def main():
    parser = argparse.ArgumentParser(description="Train hybrid ML v3 (EMA200 + setup + feedback)")
    parser.add_argument("--csv", type=str, required=True)
    parser.add_argument("--feat", choices=["v2", "ema200", "hybrid"], default="hybrid")
    parser.add_argument("--kfold", type=int, default=6)
    parser.add_argument("--db", type=str, default=str(ROOT / "data" / "bot.db"))
    parser.add_argument("--real-json", type=str, default=None,
                        help="สัญญาณจริง WIN/LOSE (dump จาก /api/ml/signals) — เรียนรู้จากผลจริง")
    parser.add_argument("--feedback", action="store_true",
                        help="เพิ่ม weight ให้แถวใกล้สัญญาณที่ยิงแล้วพลาดใน fold ก่อน")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    df_raw = load_csv(args.csv)
    df_tf = df_raw.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    df_tf.columns = ["open", "high", "low", "close", "volume"]
    print(f"ข้อมูล: {len(df_tf)} แท่ง M5 | {df_tf.index[0]} → {df_tf.index[-1]} | feat={args.feat}")

    real = load_real_signals(args.real_json) if args.real_json else []
    if real:
        print(f"สัญญาณจริงที่ใช้เรียนรู้: {len(real)} (เก่าที่สุด {real[0]['ts']})")

    X_full, y_full, cols = build_experiment(df_tf, args.feat, Path(args.db))
    print(f"Dataset: {len(X_full)} แถว | features: {len(cols)} | "
          f"balance label: {(y_full == 1).mean():.3f}")

    res = run(df_tf, X_full, y_full, cols, df_tf, args.kfold, real, args.feedback)

    s = res["summary"]
    print("\n" + "=" * 72)
    print(f"  RESULT — feat={args.feat} | folds={s['_n_folds']} | AUC_avg={s['_auc_avg']}")
    print("=" * 72)
    print(f"  {'Conf':>6} | {'n':>5} | {'Winrate':>8} | {'Net(0.82)':>10} | Breakeven {BREAKEVEN:.2f}%")
    print("  " + "-" * 55)
    gate_hit = False
    for c in CONF_GRID:
        r = s[c]
        ok = "✅" if (r["n"] >= MIN_N and r["winrate_pct"] >= GOAL_WINRATE) else ""
        if ok:
            gate_hit = True
        print(f"  {c:>6.2f} | {r['n']:>5} | {r['winrate_pct']:>7.2f}% | "
              f"{r['net_units']:>+10.2f} {ok}")

    print("\n  GATE: winrate ≥60% และ n ≥ 30 → " + ("✅ ผ่าน — พร้อมพิจารณาทับโมเดล" if gate_hit else "⛔ ยังไม่ถึง"))
    if args.out:
        Path(args.out).write_text(json.dumps({
            "feat": args.feat, "kfold": args.kfold,
            "n_rows": int(len(X_full)), "n_features": len(cols),
            "n_real": len(real), "feedback": args.feedback,
            "summary": s,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  บันทึกผลที่ {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
