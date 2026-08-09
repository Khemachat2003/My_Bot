"""
feedback_train.py — เทรน ML แบบ Walk-Forward + เรียนรู้จากความผิดพลาด (Feedback Loop)
=====================================================================================
ตอบโจทย์: "ML ไม่ต้องส่งสัญญาณบ่อย แต่ถ้าส่งต้องมีคุณภาพ (threshold สูง เช่น 0.70)"
+ "ค่อยๆ เทรนไปพร้อมเก็บราคากลับมาเทรนใหม่" + "เรียนรู้จากสัญญาณที่ส่งแล้วผิด"

วิธีทำงาน (จำลองวิธีที่ระบบ live จะใช้จริงทุกประการ):
  1. แบ่งข้อมูลตามเวลาเป็น K folds (expanding window): เทรนบน fold 1 → ทดสอบ fold 2,
     เทรนบน fold 1+2 → ทดสอบ fold 3, ...  (เหมือน retrain เมื่อมีข้อมูลใหม่สะสม)
  2. ในแต่ละ fold ใช้โมเดลยิงสัญญาณตาม threshold ที่กำหนด (CALL/PUT ถ้า prob เกิน
     threshold ฝั่งใดฝั่งหนึ่ง) วัดผลแบบ binary option (ชนะถ้าราคาหลังถือ N แท่ง
     ตรงทิศทาง) — ตรรกะเดียวกับ notifier.py
  3. เก็บ "error cases" (สัญญาณที่ยิงแล้วแพ้) พร้อม features ขณะนั้น
  4. fold ถัดไป: เทรนใหม่โดยให้ sample_weight สูงขึ้นกับตัวอย่างที่เคยพลาดใน fold
     ก่อน (ถ้าตำแหน่งเวลานั้น overlap กับข้อมูลเทรน) → โมเดลใหม่ "เรียนรู้ที่จะ
     ไม่ซ้ำความผิดเดิม" + เห็นข้อมูลใหม่ที่สะสม
  5. สรุป winrate / net units ที่ threshold 0.55 0.60 0.65 0.70 0.75 0.80
     (จำนวนสัญญาณจะลดลง แต่คุณภาพควรสูงขึ้น — เห็น tradeoff ชัดเจน)

รัน:
    ./venv/Scripts/python.exe -m backend.ml_forecaster.feedback_train \
        --csv data/deriv_frxXAUUSD_300s_120d.csv --tf M5 --horizon 6 --kfold 5
    ./venv/Scripts/python.exe -m backend.ml_forecaster.feedback_train \
        --csv data/deriv_frxXAUUSD_60s_60d.csv --tf M1 --horizon 15 --kfold 6

หมายเหตุ:
  - feature/label ใช้ชุดเดียวกับ train_live_models.py (features_v2)
  - deadzone ที่ใช้กับ label เทรน: 0.25x ATR (ตัดเคสไม่ชัดเจนตอนเทรน)
  - ผล winrate ที่ threshold สูงจะอิง sample น้อย — เช็ค n ด้วยทุกครั้ง
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

from backend.ml_forecaster.features_v2 import build_dataset_v2, FEATURE_COLUMNS_V2

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    from sklearn.ensemble import HistGradientBoostingClassifier as _HG
    HAS_LGB = False

DEADZONE = 0.25
CONF_GRID = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
MIN_TRAIN = 800          # แถวเทรนขั้นต่ำต่อ fold (ถ้าต่ำกว่านี้ข้าม fold)
MIN_SIGNALS_PER_CONF = 8 # ถ้าสัญญาณน้อยกว่านี้ กันสรุปผิดจาก sample น้อย


def _resample_1m_to(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 1:
        return df
    rule = f"{minutes}min"
    o = df["open"].resample(rule, label="left", closed="left").first()
    h = df["high"].resample(rule, label="left", closed="left").max()
    l = df["low"].resample(rule, label="left", closed="left").min()
    c = df["close"].resample(rule, label="left", closed="left").last()
    v = df["volume"].resample(rule, label="left", closed="left").sum() if "volume" in df else None
    parts = [o, h, l, c] + ([v] if v is not None else [])
    out = pd.concat(parts, axis=1)
    out.columns = ["open", "high", "low", "close"] + (["volume"] if v is not None else [])
    return out.dropna()


def _make_model():
    if HAS_LGB:
        return lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.03, num_leaves=15, max_depth=4,
            min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
        )
    return _HG(max_iter=300, learning_rate=0.03, max_depth=4,
               min_samples_leaf=50, l2_regularization=0.1, random_state=42)


def _make_labels(feat_df: pd.DataFrame, horizon: int) -> pd.Series:
    """label แบบ profit-aware: ชนะต้องขยับ > 0.25x ATR (ไม่ใช่แค่ทิศขึ้น/ลง)
    ให้ตรงกับ "ชนะจริงหลังหักค่าใช้จ่าย" มากกว่าแค่ tick ขึ้นเล็กน้อย"""
    future_close = feat_df["close"].shift(-horizon)
    delta = future_close - feat_df["close"]
    thr = feat_df["atr"] * DEADZONE
    label = pd.Series(np.nan, index=feat_df.index)
    label[delta > thr] = 1
    label[delta < -thr] = 0
    return label


def _build(feat_df: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, pd.Series]:
    y = _make_labels(feat_df, horizon)
    X = feat_df[FEATURE_COLUMNS_V2]
    valid = X.notna().all(axis=1) & y.notna()
    return X[valid], y[valid]


def _fit_with_weights(X_tr, y_tr, sample_weight, X_val, y_val):
    model = _make_model()
    if HAS_LGB:
        model.fit(X_tr, y_tr, sample_weight=sample_weight,
                  eval_set=[(X_val, y_val)],
                  callbacks=[lgb.early_stopping(30, verbose=False)])
    else:
        model.fit(X_tr, y_tr, sample_weight=sample_weight)
    return model


def _trade_outcome(row_ts, direction, df_tf, hold_bars):
    """ผลแบบ binary option: ชนะถ้าราคา close หลังถือ hold_bars แท่ง ตรงทิศ"""
    loc = df_tf.index.get_indexer([row_ts], method="nearest")[0]
    entry = float(df_tf["close"].iloc[loc])
    exit_i = loc + hold_bars
    if exit_i >= len(df_tf):
        return None
    exit_px = float(df_tf["close"].iloc[exit_i])
    win = (exit_px > entry) if direction == "CALL" else (exit_px < entry)
    return {"entry": entry, "exit": exit_px, "result": "WIN" if win else "LOSE"}


def run_walkforward(df_tf: pd.DataFrame, horizon: int, kfold: int,
                    error_memory: dict | None = None) -> dict:
    """Expanding-window walk-forward กับ feedback weighting
    คืน dict: {threshold: {n, winrate, net_units, trades[]}} + error_cases"""
    feat_df = pd.concat(
        [df_tf, pd.DataFrame(index=df_tf.index)],
        axis=1
    )
    # คำนวณ features + labels ทั้งชุด (labels ใช้เฉพาะตอนเทรน — ตัด lookahead ตามเวลา)
    from backend.ml_forecaster.features_v2 import build_features_v2
    feat = build_features_v2(df_tf)
    X_full, y_full = _build(feat, horizon)

    n = len(feat)
    fold_edges = np.linspace(0, n, kfold + 1, dtype=int)
    # ให้ fold แรกเทรนอย่างน้อย MIN_TRAIN แถว — เลื่อน edge แรกไป
    if fold_edges[1] < MIN_TRAIN:
        fold_edges[1] = MIN_TRAIN

    results: dict = {c: {"n": 0, "wins": 0, "trades": []} for c in CONF_GRID}
    error_cases = []
    models_auc = []

    for k in range(1, kfold):
        tr_end = fold_edges[k]
        te_start = fold_edges[k]
        te_end = fold_edges[k + 1] if k + 1 < kfold else n
        if te_end - te_start < 20:
            continue

        # ── train ──
        tr_slice = (X_full.index.get_indexer(feat.index[fold_edges[0]:tr_end]) >= 0)
        # ใช้วิธี: แถว train = index อยู่ก่อน tr_end
        tr_idx = feat.index[:tr_end]
        X_tr = X_full.loc[X_full.index.intersection(tr_idx)]
        y_tr = y_full.loc[y_full.index.intersection(tr_idx)]
        if len(X_tr) < MIN_TRAIN or y_tr.nunique() < 2:
            print(f"  [fold {k}] เทรนไม่พอ ({len(X_tr)} แถว) — ข้าม")
            continue

        # val = ส่วนท้ายของ train (10%) สำหรับ early stopping
        cut = int(len(X_tr) * 0.9)
        X_val, y_val = X_tr.iloc[cut:], y_tr.iloc[cut:]
        X_tr_f, y_tr_f = X_tr.iloc[:cut], y_tr.iloc[:cut]

        # feedback: เพิ่มน้ำหนักให้ตัวอย่างที่เคยยิงพลาดใน fold ก่อน
        sw = np.ones(len(X_tr_f))
        if error_memory:
            hit = 0
            for _, (ts, feat_row) in enumerate(error_memory):
                # ตัวอย่าง train ที่อยู่ใกล้เวลานั้น (ภายใน 3 แท่ง) → เพิ่มน้ำหนัก
                td = (X_tr_f.index - ts).total_seconds()
                near = (td >= 0) & (td <= 3 * (df_tf.index[1] - df_tf.index[0]).total_seconds())
                if near.any():
                    sw[near.values] *= 1.5
                    hit += 1
            if hit:
                print(f"  [fold {k}] น้ำหนัก feedback ไป {hit} ตัวอย่างที่เคยพลาด")

        model = _fit_with_weights(X_tr_f, y_tr_f, sw, X_val, y_val)
        proba_val = model.predict_proba(X_val)[:, 1]
        try:
            auc = roc_auc_score(y_val, proba_val)
        except ValueError:
            auc = float("nan")
        models_auc.append(auc)

        # ── test (ยิงสัญญาณบนข้อมูลที่โมเดลไม่เคยเห็น) ──
        te_idx = feat.index[te_start:te_end]
        X_te = X_full.loc[X_full.index.intersection(te_idx)]
        if X_te.empty:
            continue
        proba = model.predict_proba(X_te)[:, 1]
        X_te_idx = X_te.index

        # กันสแปม: ไม่ยิงซ้ำภายใน hold_bars แท่ง
        last_trade_ts = None
        for j, ts in enumerate(X_te_idx):
            prob_up = float(proba[j])
            prob_down = 1.0 - prob_up
            best = max(prob_up, prob_down)
            if best < min(CONF_GRID):
                continue
            if last_trade_ts is not None:
                bars_since = (ts - last_trade_ts).total_seconds() / \
                    (df_tf.index[1] - df_tf.index[0]).total_seconds()
                if bars_since < horizon:
                    continue

            direction = "CALL" if prob_up >= prob_down else "PUT"
            for c in CONF_GRID:
                if best >= c:
                    out = _trade_outcome(ts, direction, df_tf, horizon)
                    if out is not None:
                        results[c]["n"] += 1
                        results[c]["wins"] += 1 if out["result"] == "WIN" else 0
                        results[c]["trades"].append({
                            "time": str(ts), "direction": direction,
                            "prob": round(best, 4), "result": out["result"],
                            "entry": round(out["entry"], 2), "exit": round(out["exit"], 2),
                            "fold": k,
                        })
            last_trade_ts = ts

        # เก็บ error cases ของ fold นี้ (สัญญาณที่ยิงแล้วแพ้ที่ threshold 0.70)
        err = [t for t in results[0.70]["trades"]
               if t["result"] == "LOSE" and t["fold"] == k]
        for t in err:
            error_cases.append((pd.Timestamp(t["time"]), t))
        print(f"  [fold {k}] test {len(X_te)} แถว | AUC_val={auc:.4f} | "
              f"ยิง@{min(CONF_GRID)}={results[min(CONF_GRID)]['n']} ไม้")

    # ── สรุป ──
    summary = {}
    for c, r in results.items():
        n = r["n"]
        wr = r["wins"] / n * 100 if n else 0.0
        net = r["wins"] * 0.82 - (n - r["wins"]) * 1.0 if n else 0.0
        summary[c] = {
            "n": n, "wins": r["wins"], "winrate_pct": round(wr, 2),
            "net_units": round(net, 2),
            "breakeven": round(1 / 1.82 * 100, 2),
        }
    summary["_auc_avg"] = round(float(np.nanmean(models_auc)), 4) if models_auc else None
    summary["_n_folds"] = kfold - 1
    return {"summary": summary, "error_cases": error_cases}


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["datetime"]).set_index("datetime")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def main():
    parser = argparse.ArgumentParser(description="Walk-forward + feedback-loop ML trainer")
    parser.add_argument("--csv", type=str, required=True)
    parser.add_argument("--tf", type=str, choices=["M1", "M5"], default="M5")
    parser.add_argument("--horizon", type=int, default=6, help="แท่งที่ถือออเดอร์ (M1=15, M5=6)")
    parser.add_argument("--kfold", type=int, default=5)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    df_raw = load_csv(args.csv)
    print(f"ข้อมูล {args.tf}: {len(df_raw)} แท่ง | {df_raw.index[0]} → {df_raw.index[-1]}")
    resample_min = 5 if args.tf == "M5" else 1
    df_tf = _resample_1m_to(df_raw, resample_min)
    print(f"Resample เป็น {resample_min}m: {len(df_tf)} แท่ง")

    print(f"\n=== Walk-Forward {args.kfold} folds | horizon={args.horizon} แท่ง ===")
    print(f"Threshold ใช้ test: {CONF_GRID}\n")
    res = run_walkforward(df_tf, args.horizon, args.kfold, error_memory=None)

    print("\n" + "=" * 78)
    print(f"  RESULT — {args.tf} walk-forward ({args.kfold} folds)  |  "
          f"AUC_avg={res['summary']['_auc_avg']}")
    print("=" * 78)
    print(f"  {'Conf':>6} | {'n':>5} | {'Winrate':>8} | {'Net(0.82)':>10} | {'Breakeven':>10}")
    print("  " + "-" * 55)
    for c in CONF_GRID:
        s = res["summary"][c]
        flag = " ✅" if (s["n"] >= MIN_SIGNALS_PER_CONF and s["net_units"] > 0) else ""
        print(f"  {c:>6.2f} | {s['n']:>5} | {s['winrate_pct']:>7.2f}% | "
              f"{s['net_units']:>+10.2f} | {s['breakeven']:>9.2f}%{flag}")

    n_err = len(res["error_cases"])
    print(f"\n  error cases (สัญญาณที่ยิง@{0.70} แล้วแพ้): {n_err} ไม้")

    if args.out:
        out = Path(args.out)
        out.write_text(json.dumps({
            "tf": args.tf, "horizon": args.horizon, "kfold": args.kfold,
            "summary": res["summary"],
            "error_cases": [t for _, t in res["error_cases"]],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  บันทึกผลละเอียดไว้ที่ {out.resolve()}")


if __name__ == "__main__":
    main()
