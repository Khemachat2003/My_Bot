"""
train_walkforward.py — ประเมินโมเดลด้วย walk-forward (rolling-origin) validation
แทนการแบ่ง train/val/test แบบ split เดียว (three_way_split ใน train_validate_v2.py)

ทำไมต้องมีตัวนี้เพิ่ม:
  - three_way_split เดิม แบ่งข้อมูล "ครั้งเดียว" แล้ววัด test แค่ก้อนเดียวก้อนเดียว
    ถ้าข้อมูลมีน้อย (เช่นตอนนี้ cache มีแค่ ~1,800 แท่ง ~1.3 วัน) ก้อน test จะเหลือ
    ไม่กี่ร้อยแถว → ตัวเลข winrate ที่ได้ "โชคดี/โชคร้าย" ได้ง่ายมาก ไม่ใช่ค่าที่เชื่อได้
  - Walk-forward จำลองการใช้งานจริง: เทรนบนอดีต → เทรดบนอนาคตที่โมเดลไม่เคยเห็น →
    เลื่อนหน้าต่างไปเรื่อยๆ แล้วรวมผลทุก fold เข้าด้วยกัน ได้ sample size ใหญ่ขึ้น
    และเห็นว่าโมเดล "เสถียร" ข้ามช่วงเวลา/สภาวะตลาดต่างกันไหม ไม่ใช่ดีแค่ช่วงเดียว

ก่อนรันตัวนี้ให้มีข้อมูลเยอะที่สุดเท่าที่จะทำได้ก่อน:
    python -m backend.data_feed.backfill --days 60
(ดึงได้กี่วันจริงขึ้นกับ Deriv เก็บย้อนหลังให้แค่ไหน สำหรับ frxXAUUSD 1 นาที)

รัน:
    python -m backend.ml_forecaster.train_walkforward --horizon 5 --deadzone 0.3 --payout 0.85
"""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from backend.ml_forecaster.features_v2 import build_dataset_v2, FEATURE_COLUMNS_V2

warnings.filterwarnings("ignore")

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False
    from sklearn.ensemble import HistGradientBoostingClassifier

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CONF_GRID = [0.52, 0.55, 0.58, 0.60, 0.63, 0.65, 0.68, 0.70]


def load_price_data(min_candles: int = 200) -> pd.DataFrame:
    cache_path = DATA_DIR / "deriv_frxXAUUSD_60s.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, index_col="datetime", parse_dates=True)
        if len(df) >= min_candles:
            return df
    from backend.data_feed.deriv_feed import fetch_candles_history
    return fetch_candles_history(granularity=60, count=5000)


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
            min_samples_leaf=50, l2_regularization=0.1, random_state=42,
        )
        model.fit(X_tr, y_tr)
    return model


def pick_best_threshold(y_val, proba_val, min_signals):
    best = {"conf": None, "winrate": 0.0, "n": 0}
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


def evaluate(y, proba, conf):
    if conf is None:
        return {"n": 0, "wins": 0, "losses": 0}
    mask = (proba >= conf) | (proba <= (1 - conf))
    n = mask.sum()
    if n == 0:
        return {"n": 0, "wins": 0, "losses": 0}
    pred = np.where(proba[mask] >= conf, 1, 0)
    correct = (pred == y.values[mask])
    return {"n": int(n), "wins": int(correct.sum()), "losses": int((~correct).sum())}


def make_folds(n_rows: int, n_folds: int, min_train: int):
    """expanding-window folds: train=[0:a), val=[a:b), test=[b:c)
    เลื่อน a,b,c ไปเรื่อยๆ แบบ non-overlapping test blocks ครอบคลุมข้อมูลทั้งหมด
    หลัง min_train แถวแรก (กัน fold แรกๆ มี train น้อยเกินจนโมเดลไม่มีความหมาย)
    """
    usable = n_rows - min_train
    if usable < n_folds * 20:
        n_folds = max(1, usable // 40)
    block = usable // (n_folds + 1)  # +1 เพราะ fold แรกใช้ block นึงเป็น val ด้วย
    folds = []
    for i in range(n_folds):
        train_end = min_train + i * block
        val_end = train_end + block
        test_end = val_end + block if i < n_folds - 1 else n_rows
        if val_end >= n_rows or train_end < min_train:
            continue
        folds.append((0, train_end, train_end, val_end, val_end, min(test_end, n_rows)))
    return folds


def wilson_ci(wins: int, n: int, z: float = 1.96):
    if n == 0:
        return None, None
    p = wins / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    margin = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    return (center - margin) / denom * 100, (center + margin) / denom * 100


def walkforward_eval(X: pd.DataFrame, y: pd.Series, n_folds: int) -> dict:
    """รัน walk-forward เต็มรูปแบบบน (X, y) ที่ให้มา คืนค่า fold_rows + สถิติรวม
    ไม่ print อะไรเอง (ให้ผู้เรียกเลือกจะแสดงผลแบบไหนก็ได้) — ใช้ร่วมกันได้ทั้ง
    train_walkforward.py (config เดียว, print ละเอียด) และ config_search.py
    (หลาย config, เทียบกันเป็นตาราง)
    """
    min_train = max(300, int(len(X) * 0.3))
    folds = make_folds(len(X), n_folds=n_folds, min_train=min_train)
    if not folds:
        return {"fold_rows": [], "n_total": 0, "wins": 0, "losses": 0, "pooled_winrate": None,
                 "ci_low": None, "ci_high": None}

    fold_rows = []
    total_wins = total_losses = 0
    for i, (tr0, tr1, v0, v1, t0, t1) in enumerate(folds, 1):
        X_tr, y_tr = X.iloc[tr0:tr1], y.iloc[tr0:tr1]
        X_val, y_val = X.iloc[v0:v1], y.iloc[v0:v1]
        X_test, y_test = X.iloc[t0:t1], y.iloc[t0:t1]
        if y_tr.nunique() < 2 or len(X_val) < 20 or len(X_test) < 20:
            continue

        model = make_and_fit(X_tr, y_tr, X_val, y_val)
        proba_val = model.predict_proba(X_val)[:, 1]
        proba_test = model.predict_proba(X_test)[:, 1]

        auc_test = roc_auc_score(y_test, proba_test) if y_test.nunique() > 1 else float("nan")
        min_signals = max(10, int(len(X_val) * 0.03))
        chosen = pick_best_threshold(y_val, proba_val, min_signals)
        res = evaluate(y_test, proba_test, chosen["conf"])

        total_wins += res["wins"]
        total_losses += res["losses"]
        period = f"{X_test.index[0]:%Y-%m-%d %H:%M} → {X_test.index[-1]:%Y-%m-%d %H:%M}"
        wr = 100 * res["wins"] / res["n"] if res["n"] else None
        fold_rows.append({
            "fold": i, "test_period": period, "conf_used": chosen["conf"],
            "n_signals": res["n"], "wins": res["wins"], "losses": res["losses"],
            "winrate_%": round(wr, 1) if wr is not None else None,
            "auc_test": round(auc_test, 4) if not np.isnan(auc_test) else None,
        })

    n_total = total_wins + total_losses
    pooled_winrate = 100 * total_wins / n_total if n_total else None
    ci_low, ci_high = wilson_ci(total_wins, n_total) if n_total else (None, None)
    return {
        "fold_rows": fold_rows, "n_total": n_total, "wins": total_wins, "losses": total_losses,
        "pooled_winrate": pooled_winrate, "ci_low": ci_low, "ci_high": ci_high,
    }


def run(horizon: int, deadzone: float, payout: float, n_folds: int):
    raw_df = load_price_data()
    n_days_approx = len(raw_df) / (24 * 60)
    print(f"[WF] ข้อมูลดิบ: {len(raw_df)} แท่ง (≈{n_days_approx:.1f} วัน ของแท่ง 1 นาที)")
    if n_days_approx < 14:
        print(f"[WF] ⚠️ ข้อมูลน้อยกว่า 14 วัน — ผลลัพธ์ด้านล่างมี noise สูงมาก "
              f"แนะนำรัน `python -m backend.data_feed.backfill --days 60` ก่อนเชื่อตัวเลขนี้จริงจัง\n")

    X, y = build_dataset_v2(raw_df, horizon=horizon, deadzone_atr_mult=deadzone,
                             feature_columns=FEATURE_COLUMNS_V2)
    print(f"[WF] หลังตัด warm-up/deadzone เหลือ {len(X)} แถวใช้ได้\n")
    print(f"[WF] horizon={horizon}m deadzone={deadzone}xATR payout={payout} "
          f"model={'LightGBM' if HAS_LGB else 'sklearn-fallback'}\n")

    result = walkforward_eval(X, y, n_folds)
    if not result["fold_rows"]:
        print("[WF] ข้อมูลน้อยเกินไป หรือทุก fold มีข้อมูลไม่พอ ไม่สามารถประเมินได้")
        return

    df_res = pd.DataFrame(result["fold_rows"])
    print(df_res.to_string(index=False))

    n_total, pooled_winrate = result["n_total"], result["pooled_winrate"]
    print(f"\n{'=' * 70}")
    if n_total == 0:
        print("รวมทุก fold: ไม่มีสัญญาณเลย")
        return
    print(f"รวมทุก fold: signals={n_total}  wins={result['wins']}  losses={result['losses']}  "
          f"pooled winrate={pooled_winrate:.1f}%")

    # breakeven winrate ของ binary option: payout คือกำไร % ถ้าถูก (เช่น 0.85 = ได้ 85%
    # ของเงินเดิมพันคืนมาเป็นกำไร), ถ้าผิดเสียเงินเดิมพัน 100%
    breakeven = 1 / (1 + payout) * 100
    expectancy_per_trade = (pooled_winrate / 100 * payout) - ((1 - pooled_winrate / 100) * 1)
    print(f"breakeven winrate ที่ payout={payout} ต้องการ: {breakeven:.1f}%")

    ci_low, ci_high = result["ci_low"], result["ci_high"]
    print(f"95% CI ของ pooled winrate: [{ci_low:.1f}%, {ci_high:.1f}%]  (n={n_total})")

    if ci_high < breakeven:
        print(f"❌ ทั้งช่วง CI ต่ำกว่า breakeven ({breakeven:.1f}%) — ข้อมูลตอนนี้บอกว่ายังไม่มี edge จริงพอจะคุ้มทุน")
    elif ci_low > breakeven:
        print(f"✅ ทั้งช่วง CI สูงกว่า breakeven — expectancy ≈ {expectancy_per_trade:+.3f} หน่วย/เทรด "
              f"(สัญญาณที่ดี แต่ยังควรยืนยันซ้ำกับข้อมูลช่วงใหม่ก่อนใช้เงินจริง)")
    else:
        print(f"⚠️ breakeven ({breakeven:.1f}%) อยู่ในช่วง CI — สรุปไม่ได้ชัดเจนว่ามี edge คุ้มทุนหรือไม่ "
              f"จากข้อมูลเท่านี้ (ไม่ใช่ 'พิสูจน์แล้วว่าใช้ไม่ได้' แต่ก็ไม่ใช่ 'พิสูจน์แล้วว่าคุ้ม' — ต้องการข้อมูล/หลักฐานเพิ่ม)")

    valid_wr = df_res.dropna(subset=["winrate_%"])
    if len(valid_wr) > 1:
        print(f"ความเสถียรระหว่าง fold: winrate ต่ำสุด={valid_wr['winrate_%'].min()}%  "
              f"สูงสุด={valid_wr['winrate_%'].max()}%  "
              f"(ถ้าห่างกันมาก แปลว่าโมเดลไม่เสถียรข้ามช่วงเวลา ยังไม่ควรเชื่อ)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--deadzone", type=float, default=0.3)
    parser.add_argument("--payout", type=float, default=0.85,
                         help="อัตราจ่ายจริงของโบรกเกอร์ตอนทายถูก เช่น 0.85 = ได้กำไร 85%% ของเงินเดิมพัน")
    parser.add_argument("--folds", type=int, default=6)
    args = parser.parse_args()
    run(args.horizon, args.deadzone, args.payout, args.folds)


if __name__ == "__main__":
    main()
