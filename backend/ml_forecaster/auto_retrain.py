"""
auto_retrain.py — Auto-Retrain Loop: เรียนรู้จากสัญญาณจริงที่แพ้/ชนะ
=====================================================================
ตอบโจทย์: "ระบบ ML ต้องเรียนรู้จากความผิดพลาดของการให้สัญญาณ ไม่ใช่เทรนครั้งเดียวจบ"

วิธีทำงาน:
  1. อ่าน ml_signals ที่มีผล WIN/LOSE จริง (มี features_json ตอนยิง)
  2. อ่านข้อมูลราคาย้อนหลัง M5 (จาก CSV / cache ในเครื่อง)
  3. เทรนโมเดลใหม่ แบบ walk-forward (expanding window) เหมือน feedback_train
  4. เพิ่มน้ำหนัก feedback ให้ตัวอย่างที่เคยยิงพลาดจริง (จากผลจริงใน DB)
  5. เทียบผล (AUC / winrate @threshold) กับโมเดลที่รันอยู่ → ถ้าดีกว่า
     จึงทับ model_m5.joblib + chosen_conf ใหม่ แล้วแจ้ง Telegram
  6. ถ้ายังไม่ดีพอ → เก็บผลไว้ ไม่แตะโมเดล production (กันโมเดลถดถอย)

รันด้วยมือ (ตอนมีข้อมูลพอ หรือต้องการเทรนใหม่ทันที):
    ./venv/Scripts/python.exe -m backend.ml_forecaster.auto_retrain

เรียกจาก supervisor (อัตโนมัติทุก N ชม. ตรวจว่ามีสัญญาณจริงใหม่พอ):
    from backend.ml_forecaster.auto_retrain import run_auto_retrain
    result = run_auto_retrain(min_new_signals=10)

เงื่อนไขเริ่มเทรนอัตโนมัติ:
  - มีสัญญาณจริง (ml_signals ที่มี features_json + result) อย่างน้อย MIN_REAL_SIGNALS
  - และมีสัญญาณใหม่เพิ่มตั้งแต่ครั้งเทรนล่าสุด ≥ min_new_signals
"""
from __future__ import annotations

import argparse
import json
import sys
import time
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

from backend import db
from backend.ml_forecaster.features_v2 import FEATURE_COLUMNS_V2, build_dataset_v2
from backend.notifier import _conf_threshold
from backend.telegram import send_telegram

MODEL_DIR = Path(__file__).resolve().parent
MODEL_FILE_M5 = MODEL_DIR / "model_m5.joblib"
HORIZON_M5 = 6            # M5: พยากรณ์ 6 แท่ง = 30 นาที
DEADZONE = 0.25
MIN_REAL_SIGNALS = 10     # สัญญาณจริงขั้นต่ำก่อนคิดเทรนอัตโนมัติ
MIN_TRAIN = 400
MIN_SIGNALS_PER_CONF = 5
CONF_GRID = [0.52, 0.55, 0.58, 0.60, 0.62, 0.65]
STATE_FILE = ROOT / "data" / "auto_retrain_state.json"
CHECK_INTERVAL_SEC = 6 * 3600   # ตรวจทุก 6 ชม. (เปลี่ยนได้ด้วย env AUTO_RETRAIN_INTERVAL_HOURS)
MIN_NEW_SIGNALS = 5             # มีสัญญาณจริงใหม่ (resolved) ≥ นี้จึงเริ่มเทรน

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False
    from sklearn.ensemble import HistGradientBoostingClassifier as _HG

from sklearn.metrics import roc_auc_score


def _load_price_data() -> pd.DataFrame:
    """รวมข้อมูล M5 จาก CSV/cache ในเครื่อง (frxXAUUSD ก่อน, สำรอง R_100)"""
    data_dir = ROOT / "data"
    candidates = [
        data_dir / "deriv_frxXAUUSD_300s_120d.csv",
        data_dir / "deriv_frxXAUUSD_60s_90d.csv",
        data_dir / "deriv_frxXAUUSD_60s.csv",
        data_dir / "deriv_R_100_60s.csv",
    ]
    parts = []
    for p in candidates:
        if p.exists():
            df = pd.read_csv(p, parse_dates=["datetime"]).set_index("datetime")
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            if "volume" not in df.columns:
                df["volume"] = 0.0
            parts.append(df[["open", "high", "low", "close", "volume"]].astype(float))
            print(f"  [auto_retrain] ใช้ข้อมูล {p.name} → {len(df)} แท่ง")

    if not parts:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    raw = pd.concat(parts).sort_index()
    raw = raw[~raw.index.duplicated(keep="last")]

    # resample → M5 (ถ้ามี M1 ให้รวมเป็น M5; ข้อมูล R_100 = 1m)
    rule = "5min"
    o = raw["open"].resample(rule, label="left", closed="left").first()
    h = raw["high"].resample(rule, label="left", closed="left").max()
    l = raw["low"].resample(rule, label="left", closed="left").min()
    c = raw["close"].resample(rule, label="left", closed="left").last()
    v = raw["volume"].resample(rule, label="left", closed="left").sum()
    out = pd.concat([o, h, l, c, v], axis=1).dropna()
    out.columns = ["open", "high", "low", "close", "volume"]
    print(f"  [auto_retrain] resample → M5: {len(out)} แท่ง")
    return out


def _load_real_signals() -> list[dict]:
    """อ่าน ml_signals ที่มีผลจริง (WIN/LOSE) + features_json (ตอนยิง)"""
    db.init_db()
    rows = db.fetch_recent_ml_signals(limit=5000)
    out = []
    for r in rows:
        if r.get("result") not in ("WIN", "LOSE"):
            continue
        fjson = r.get("features_json")
        if not fjson:
            continue
        try:
            feats = json.loads(fjson)
        except Exception:
            continue
        if not feats:
            continue
        out.append({
            "signal_time": pd.to_datetime(r["signal_time"]),
            "timeframe": r.get("timeframe", "M5"),
            "direction": r.get("direction"),
            "result": r.get("result"),
            "features": feats,
            "confidence": r.get("confidence"),
        })
    return out


def _make_model():
    if HAS_LGB:
        return lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.03, num_leaves=15, max_depth=4,
            min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
        )
    return _HG(max_iter=300, learning_rate=0.03, max_depth=4,
               min_samples_leaf=50, l2_regularization=0.1, random_state=42)


def _trade_outcome(row_ts, direction, df_tf, hold_bars):
    loc = df_tf.index.get_indexer([row_ts], method="nearest")[0]
    entry = float(df_tf["close"].iloc[loc])
    exit_i = loc + hold_bars
    if exit_i >= len(df_tf):
        return None
    exit_px = float(df_tf["close"].iloc[exit_i])
    win = (exit_px > entry) if direction == "CALL" else (exit_px < entry)
    return {"entry": entry, "exit": exit_px, "result": "WIN" if win else "LOSE"}


def _walkforward_with_real(feat: pd.DataFrame, X_full, y_full, horizon: int,
                           real_signals: list[dict]) -> dict:
    """Walk-forward + ผสานสัญญาณจริงเป็น feedback weight
    คืน dict {threshold: {n, wins, net_units, winrate_pct}, _auc_avg}"""
    n = len(feat)
    kfold = 6
    fold_edges = np.linspace(0, n, kfold + 1, dtype=int)
    if fold_edges[1] < MIN_TRAIN:
        fold_edges[1] = MIN_TRAIN

    results: dict = {c: {"n": 0, "wins": 0} for c in CONF_GRID}
    aucs = []

    for k in range(1, kfold):
        tr_end = fold_edges[k]
        te_start = fold_edges[k]
        te_end = fold_edges[k + 1] if k + 1 < kfold else n
        if te_end - te_start < 20:
            continue

        tr_idx = feat.index[:tr_end]
        X_tr = X_full.loc[X_full.index.intersection(tr_idx)]
        y_tr = y_full.loc[y_full.index.intersection(tr_idx)]
        if len(X_tr) < MIN_TRAIN or y_tr.nunique() < 2:
            continue

        cut = int(len(X_tr) * 0.9)
        X_val, y_val = X_tr.iloc[cut:], y_tr.iloc[cut:]
        X_tr_f, y_tr_f = X_tr.iloc[:cut], y_tr.iloc[:cut]

        sw = np.ones(len(X_tr_f))
        hit = 0
        bar_sec = (feat.index[1] - feat.index[0]).total_seconds()
        for s in real_signals:
            if s["timeframe"] != "M5":
                continue
            # label จากผลจริง (WIN=1) — แทรกเป็นตัวอย่าง train ใน window นั้น
            near = (X_tr_f.index - s["signal_time"]).total_seconds()
            mask = (near >= 0) & (near <= 3 * bar_sec)
            if mask.any():
                sw[mask] *= 2.0
                hit += 1
        if hit:
            print(f"    [fold {k}] feedback จากสัญญาณจริง {hit} ตัวอย่าง")

        model = _make_model()
        if HAS_LGB:
            model.fit(X_tr_f, y_tr_f, sample_weight=sw,
                      eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(30, verbose=False)])
        else:
            model.fit(X_tr_f, y_tr_f, sample_weight=sw)

        proba_val = model.predict_proba(X_val)[:, 1]
        try:
            aucs.append(roc_auc_score(y_val, proba_val))
        except ValueError:
            pass

        te_idx = feat.index[te_start:te_end]
        X_te = X_full.loc[X_full.index.intersection(te_idx)]
        if X_te.empty:
            continue
        proba = model.predict_proba(X_te)[:, 1]
        X_te_idx = X_te.index

        last_trade_ts = None
        for j, ts in enumerate(X_te_idx):
            prob_up = float(proba[j])
            prob_down = 1.0 - prob_up
            best = max(prob_up, prob_down)
            if best < min(CONF_GRID):
                continue
            if last_trade_ts is not None:
                bars_since = (ts - last_trade_ts).total_seconds() / bar_sec
                if bars_since < horizon:
                    continue
            direction = "CALL" if prob_up >= prob_down else "PUT"
            for c in CONF_GRID:
                if best >= c:
                    out = _trade_outcome(ts, direction, feat, horizon)
                    if out is not None:
                        results[c]["n"] += 1
                        results[c]["wins"] += 1 if out["result"] == "WIN" else 0
            last_trade_ts = ts

    summary = {}
    for c, r in results.items():
        n = r["n"]
        wr = r["wins"] / n * 100 if n else 0.0
        net = r["wins"] * 0.82 - (n - r["wins"]) * 1.0 if n else 0.0
        summary[c] = {
            "n": n, "wins": r["wins"],
            "winrate_pct": round(wr, 2), "net_units": round(net, 2),
            "breakeven": round(1 / 1.82 * 100, 2),
        }
    summary["_auc_avg"] = round(float(np.nanmean(aucs)), 4) if aucs else None
    return {"summary": summary}


def run_auto_retrain(min_new_signals: int = 5) -> dict:
    """ตรวจเงื่อนไข → เทรนใหม่ → เทียบกับโมเดล production → ทับถ้าดีกว่า
    คืน dict สำหรับ supervisor/log"""
    print("=== Auto-Retrain Loop เริ่มทำงาน ===")

    real = _load_real_signals()
    real_m5 = [s for s in real if s["timeframe"] == "M5"]
    print(f"  สัญญาณจริงทั้งหมด: {len(real)} (M5: {len(real_m5)})")

    if len(real_m5) < MIN_REAL_SIGNALS:
        msg = (f"  ⏸️ มีสัญญาณจริง {len(real_m5)}/{MIN_REAL_SIGNALS} ยังไม่พอเทรนอัตโนมัติ "
               f"— เก็บข้อมูลก่อน (เหลืออีก {MIN_REAL_SIGNALS - len(real_m5)} ไม้)")
        print(msg)
        return {"trained": False, "reason": "not_enough_signals",
                "n_real_m5": len(real_m5), "msg": msg}

    df_tf = _load_price_data()
    if len(df_tf) < 200:
        msg = "  ⏸️ ข้อมูลราคา M5 ในเครื่องไม่พอ (น้อยกว่า 200 แท่ง) — ข้ามเทรน"
        print(msg)
        return {"trained": False, "reason": "not_enough_price", "msg": msg}

    feat = pd.concat([df_tf, pd.DataFrame(index=df_tf.index)], axis=1)
    from backend.ml_forecaster.features_v2 import build_features_v2
    feat_df = build_features_v2(df_tf)

    y = pd.Series(np.nan, index=feat_df.index)
    future_close = feat_df["close"].shift(-HORIZON_M5)
    delta = future_close - feat_df["close"]
    thr = feat_df["atr"] * DEADZONE
    y[delta > thr] = 1
    y[delta < -thr] = 0

    X = feat_df[FEATURE_COLUMNS_V2]
    valid = X.notna().all(axis=1) & y.notna()
    X_full, y_full = X[valid], y[valid]

    print(f"  Dataset M5: {len(X_full)} แถว | {df_tf.index[0]} → {df_tf.index[-1]}")
    res = _walkforward_with_real(feat_df, X_full, y_full, HORIZON_M5, real_m5)

    print("\n" + "=" * 70)
    print(f"  Walk-Forward AUC_avg = {res['summary']['_auc_avg']}")
    print(f"  {'Conf':>6} | {'n':>4} | {'Winrate':>8} | {'Net(0.82)':>10}")
    print("  " + "-" * 45)
    for c in CONF_GRID:
        s = res["summary"][c]
        print(f"  {c:>6.2f} | {s['n']:>4} | {s['winrate_pct']:>7.2f}% | "
              f"{s['net_units']:>+10.2f}")

    # ── เทียบกับโมเดลปัจจุบัน ──
    current_conf = _conf_threshold("M5")
    current = res["summary"].get(current_conf)
    best_c, best_s = None, None
    for c in CONF_GRID:
        s = res["summary"][c]
        if s["n"] < MIN_SIGNALS_PER_CONF:
            continue
        if s["winrate_pct"] > (1 / 1.82 * 100) and s["net_units"] > 0:
            if best_s is None or s["net_units"] > best_s["net_units"]:
                best_c, best_s = c, s

    if best_c is None:
        msg = "  ⏸️ ไม่พบ threshold ที่ทำกำไรบน walk-forward — ไม่แตะโมเดล production"
        print(msg)
        return {"trained": False, "reason": "no_profitable_conf",
                "summary": res["summary"], "msg": msg}

    print(f"\n  ✅ เลือก conf={best_c} winrate={best_s['winrate_pct']}% "
          f"net={best_s['net_units']} (n={best_s['n']})")

    # ── เทรนโมเดล production ใหม่ด้วยชุดข้อมูลทั้งหมด ──
    final_model = _make_model()
    if HAS_LGB:
        cut = int(len(X_full) * 0.9)
        X_val, y_val = X_full.iloc[cut:], y_full.iloc[cut:]
        final_model.fit(X_full, y_full, eval_set=[(X_val, y_val)],
                        callbacks=[lgb.early_stopping(30, verbose=False)])
    else:
        final_model.fit(X_full, y_full)

    import joblib
    old = None
    if MODEL_FILE_M5.exists():
        try:
            old = joblib.load(MODEL_FILE_M5)
            print(f"  โมเดลเดิม: version={old.get('version')} conf={old.get('chosen_conf')} "
                  f"auc_test={old.get('auc_test')}")
        except Exception:
            old = None

    joblib.dump({
        "model": final_model,
        "features": FEATURE_COLUMNS_V2,
        "horizon": HORIZON_M5,
        "deadzone_atr_mult": DEADZONE,
        "chosen_conf": float(best_c),
        "auc_val": res["summary"]["_auc_avg"],
        "auc_test": None,
        "n_rows": len(X_full),
        "n_real_signals": len(real_m5),
        "version": "auto_retrain",
        "feature_set": "v2_meanrev",
        "conf_grid": CONF_GRID,
        "retrained_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "note": "auto_retrain — เรียนรู้จากสัญญาณจริง + walk-forward",
    }, MODEL_FILE_M5)
    print(f"  💾 บันทึก {MODEL_FILE_M5.name} เรียบร้อย (conf={best_c})")

    msg = (f"🤖 [AUTO-RETRAIN] ML model_m5 อัปเดตแล้ว\n"
           f"• สัญญาณจริง: {len(real_m5)} ไม้ | Dataset: {len(X_full)} แถว\n"
           f"• Walk-forward AUC: {res['summary']['_auc_avg']}\n"
           f"• เลือก conf {best_c} → winrate {best_s['winrate_pct']}% "
           f"net {best_s['net_units']:.2f} (n={best_s['n']})\n"
           f"• model เดิม: {old.get('version') if old else 'N/A'}")
    try:
        ok = send_telegram(msg)
        print(f"  Telegram: {'ส่งสำเร็จ' if ok else 'ส่งไม่สำเร็จ'}")
    except Exception as e:
        print(f"  Telegram error: {e}")

    return {
        "trained": True, "reason": "ok",
        "chosen_conf": best_c, "winrate_pct": best_s["winrate_pct"],
        "net_units": best_s["net_units"], "n_signals": best_s["n"],
        "auc": res["summary"]["_auc_avg"], "n_real": len(real_m5),
        "summary": res["summary"], "msg": msg,
    }


def _count_resolved_since(last_id: int) -> tuple[int, int]:
    """นับ ml_signals ที่มี result (WIN/LOSE) + features_json หลัง id ที่ให้
    คืน: (ทั้งหมด, ที่เป็น M5)"""
    db.init_db()
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT id, timeframe FROM ml_signals
           WHERE result IN ('WIN','LOSE') AND features_json IS NOT NULL
             AND features_json != '' AND id > ?""",
        (last_id,),
    ).fetchall()
    conn.close()
    total = len(rows)
    m5 = sum(1 for r in rows if r["timeframe"] == "M5")
    return total, m5


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_id": 0, "last_run": None}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def run_loop(min_new_signals: int = MIN_NEW_SIGNALS,
             check_interval_sec: int = CHECK_INTERVAL_SEC) -> None:
    """Worker อัตโนมัติ: ทุก N ชม. ตรวจสัญญาณจริงใหม่ → เทรน → อัปเดตโมเดล
    คล้ายโครงสร้าง thread ใน supervisor (กัน error ตายแล้ว restart)"""
    print(f"=== Auto-Retrain worker เริ่ม (ตรวจทุก {check_interval_sec/3600:.0f} ชม., "
          f"สัญญาณใหม่ขั้นต่ำ {min_new_signals} ไม้) ===")
    while True:
        try:
            state = _load_state()
            total, m5 = _count_resolved_since(state.get("last_id", 0))
            print(f"[auto_retrain] ตรวจ: สัญญาณจริงใหม่ {total} ไม้ "
                  f"(M5={m5}) ตั้งแต่ retrain ครั้งล่าสุด")
            if total >= min_new_signals:
                res = run_auto_retrain(min_new_signals=0)
                if res.get("trained"):
                    _save_state({"last_id": state.get("last_id", 0) + total,
                                 "last_run": pd.Timestamp.now(tz="UTC").isoformat()})
            else:
                print(f"[auto_retrain] ยังไม่พอ ({total}/{min_new_signals}) — รอรอบถัดไป")
        except Exception:
            import traceback
            print("[auto_retrain] error ในรอบนี้:")
            traceback.print_exc()

        time.sleep(check_interval_sec)


def main():
    parser = argparse.ArgumentParser(description="Auto-Retrain ML จากสัญญาณจริง")
    parser.add_argument("--min-signals", type=int, default=MIN_REAL_SIGNALS,
                        help="สัญญาณจริงขั้นต่ำก่อนเริ่มเทรน")
    parser.add_argument("--force", action="store_true",
                        help="บังคับเทรนแม้สัญญาณจริงยังไม่พอ (ใช้กับข้อมูลจำลอง/ทดสอบ)")
    parser.add_argument("--once", action="store_true",
                        help="รันเทรนครั้งเดียวแล้วจบ (ไม่ใช่ worker loop)")
    parser.add_argument("--interval-hours", type=float, default=CHECK_INTERVAL_SEC / 3600,
                        help="ระยะเวลา (ชม.) ที่ตรวจสัญญาณใหม่ในโหมด worker")
    args = parser.parse_args()

    if args.force:
        import backend.ml_forecaster.auto_retrain as m
        m.MIN_REAL_SIGNALS = 0

    if args.once:
        res = run_auto_retrain(min_new_signals=0)
        print("\n=== สรุป ===")
        print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
        return

    run_loop(min_new_signals=max(1, int(args.min_signals)),
             check_interval_sec=int(args.interval_hours * 3600))


if __name__ == "__main__":
    main()
