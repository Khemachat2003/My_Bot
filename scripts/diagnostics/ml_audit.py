"""
ml_audit.py — ตรวจสุขภาพข้อมูลเทรน + ประเมินโมเดล ML แบบ READ-ONLY
====================================================================================
ทำอะไร (ไม่แตะ production):
  1. สแกนไฟล์ CSV ในเครื่อง + ตาราง prices ใน DB → รายงานช่วงเวลา / ราคา / ช่องว่าง
  2. ตรวจจับ "ข้อมูลปน symbol" ในเส้นทางที่ auto_retrain ใช้จริง
     (XAUUSD ~4,000 ปนกับ R_100 ~600) + วัดความรุนแรงของ price jump
  3. สร้างชุดข้อมูลสะอาด symbol เดียว → เทรน/ประเมินด้วย Purged Walk-Forward
     (ตัด embargo กัน label ทับกัน — ตัวเลขจะต่ำกว่าที่เคยเห็น แต่เชื่อถือได้)
  4. ตาราง Winrate vs threshold + Wilson 95% CI + net units ตาม payout จริง
  5. คำนวณจำนวนไม้ขั้นต่ำที่ต้องเก็บเพื่อพิสูจน์ winrate เป้าหมาย

วิธีใช้ (รันจาก root ของโปรเจกต์):
    python scripts/diagnostics/ml_audit.py
    python scripts/diagnostics/ml_audit.py --tf M1 --horizon 15
    python scripts/diagnostics/ml_audit.py --symbol frxXAUUSD --payout 0.82 --json reports/ml_audit.json

หมายเหตุ: ไฟล์นี้ "อ่านเท่านั้น" — ไม่เขียน DB, ไม่บันทึกโมเดล, ไม่แก้ไฟล์ข้อมูล
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # ให้ import backend.* ได้เมื่อรันตรงจาก scripts/

from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score  # noqa: E402

from backend.ml_forecaster.features_v2 import (  # noqa: E402
    FEATURE_COLUMNS_V2,
    build_dataset_v2,
)

DB_PATH = ROOT / "data" / "bot.db"
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

# ลำดับไฟล์ที่ auto_retrain._load_price_data() ใช้ ณ วันที่เขียนสคริปต์นี้
# (ถ้าแก้ loader ภายหลัง ให้อัปเดต list นี้ด้วย)
AUTO_RETRAIN_CANDIDATES = [
    "deriv_frxXAUUSD_300s_120d.csv",
    "deriv_frxXAUUSD_60s_90d.csv",
    "deriv_frxXAUUSD_60s.csv",
    "deriv_R_100_60s.csv",
]

PIPELINE = ROOT / "backend" / "ml_forecaster"

TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600}


@dataclass
class FileInfo:
    path: Path
    rows: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    close_median: float
    close_min: float
    close_max: float
    median_gap_min: float
    big_gaps: int
    max_gap_hours: float


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────
def _granularity_seconds(path: Path) -> int | None:
    m = re.search(r"_(\d+)s(?:_|\.|$)", path.name)
    return int(m.group(1)) if m else None


def _read_price_csv(path: Path) -> pd.DataFrame | None:
    """อ่าน CSV แบบทนไฟล์เสีย (coerce timestamp + ตัวเลข) — ยังไม่แก้ไฟล์ต้นทาง"""
    try:
        raw = pd.read_csv(path)
    except Exception as exc:
        print(f"  ⚠️  อ่าน {path.name} ไม่ได้: {exc}")
        return None
    if raw.empty or "datetime" not in raw.columns:
        return None
    raw["datetime"] = pd.to_datetime(raw["datetime"], errors="coerce", utc=True)
    raw = raw.dropna(subset=["datetime"])
    cols = ["open", "high", "low", "close", "volume"]
    for col in cols:
        if col not in raw.columns:
            raw[col] = 0.0
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw = raw.dropna(subset=["open", "high", "low", "close"])
    if raw.empty:
        return None
    out = raw.set_index("datetime")[cols].astype(float).sort_index()
    return out[~out.index.duplicated(keep="last")]


def _describe(path: Path, df: pd.DataFrame) -> FileInfo:
    gaps = df.index.to_series().diff().dt.total_seconds().dropna()
    med = float(gaps.median()) if len(gaps) else 0.0
    return FileInfo(
        path=path,
        rows=len(df),
        start=df.index.min(),
        end=df.index.max(),
        close_median=float(df["close"].median()),
        close_min=float(df["close"].min()),
        close_max=float(df["close"].max()),
        median_gap_min=round(med / 60, 2),
        big_gaps=int((gaps > max(med * 3, 300)).sum()) if len(gaps) else 0,
        max_gap_hours=round(float(gaps.max()) / 3600, 1) if len(gaps) else 0.0,
    )


def _fmt_ts(ts) -> str:
    return "—" if ts is None or pd.isna(ts) else pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _make_model(n_estimators: int):
    try:
        import lightgbm as lgb

        return lgb.LGBMClassifier(
            n_estimators=n_estimators,
            learning_rate=0.03,
            num_leaves=15,
            max_depth=4,
            min_child_samples=50,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=0.1,
            random_state=42,
            verbosity=-1,
        )
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingClassifier

        print("  ⚠️  ไม่มี lightgbm — ใช้ HistGradientBoosting แทน (ผลจะต่างเล็กน้อย)")
        return HistGradientBoostingClassifier(
            max_iter=n_estimators,
            learning_rate=0.03,
            max_depth=4,
            l2_regularization=0.1,
            random_state=42,
        )


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna(subset=["open", "high", "low", "close"])


def _load_db_prices(symbol: str) -> pd.DataFrame | None:
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(prices)")}
            vol = "volume" if "volume" in cols else "0.0 AS volume"
            df = pd.read_sql(
                f"SELECT ts, open, high, low, close, {vol} FROM prices "
                "WHERE symbol = ? ORDER BY ts",
                conn,
                params=(symbol,),
                parse_dates=["ts"],
            )
        finally:
            conn.close()
    except Exception as exc:
        print(f"  ⚠️  อ่าน DB ไม่ได้: {exc}")
        return None
    if df.empty:
        return None
    df = df.set_index("ts").astype(float).sort_index()
    df.index.name = "datetime"
    return df[~df.index.duplicated(keep="last")]


# ──────────────────────────────────────────────────────────────────────────────
# 1) สแกนไฟล์ + DB
# ──────────────────────────────────────────────────────────────────────────────
def section_scan(symbol: str) -> list[FileInfo]:
    wanted = set(AUTO_RETRAIN_CANDIDATES)
    paths = sorted(
        p
        for p in list(DATA_DIR.glob("deriv_*.csv")) + list(ROOT.glob("deriv_*.csv"))
        if symbol in p.name or p.name in wanted
    )
    files: list[FileInfo] = []
    print("\n" + "=" * 78)
    print("1) ไฟล์ข้อมูลในเครื่อง")
    print("=" * 78)
    print(f"{'ไฟล์':46} {'แท่ง':>7} {'ช่วงเวลา':>31} {'median':>10} {'gap สูงสุด':>10}")
    for path in paths:
        df = _read_price_csv(path)
        if df is None:
            continue
        info = _describe(path, df)
        files.append(info)
        span = f"{_fmt_ts(info.start)} → {_fmt_ts(info.end)}"
        print(
            f"{path.name:46} {info.rows:>7,} {span:>31} {info.close_median:>10,.2f}"
            f" {info.max_gap_hours:>8.1f}h"
        )

    db_df = _load_db_prices(symbol)
    if db_df is not None:
        info = _describe(DB_PATH, db_df)
        files.append(info)
        span = f"{_fmt_ts(info.start)} → {_fmt_ts(info.end)}"
        print(
            f"{'data/bot.db:prices[' + symbol + ']':46} {info.rows:>7,} {span:>31}"
            f" {info.close_median:>10,.2f} {info.max_gap_hours:>8.1f}h"
        )
        expected = int((db_df.index.max() - db_df.index.min()).total_seconds() / 60) + 1
        print(
            f"    ↳ DB ครอบคลุมช่วง {expected:,} นาที แต่มีจริง {info.rows:,} แท่ง"
            f" → ขาด {(1 - info.rows / max(expected, 1)) * 100:.1f}%"
        )
    return files


# ──────────────────────────────────────────────────────────────────────────────
# 2) ตรวจข้อมูลปน symbol ตามเส้นทาง auto_retrain
# ──────────────────────────────────────────────────────────────────────────────
def section_contamination(symbol: str) -> dict:
    print("\n" + "=" * 78)
    print("2) ตรวจเส้นทางข้อมูลที่ auto_retrain ใช้ (candidates + DB prices)")
    print("=" * 78)
    parts: list[pd.DataFrame] = []
    sources: list[str] = []
    for name in AUTO_RETRAIN_CANDIDATES:
        path = DATA_DIR / name
        if not path.exists():
            print(f"  – {name:38} ไม่มีไฟล์")
            continue
        df = _read_price_csv(path)
        if df is None:
            print(f"  – {name:38} อ่านไม่ได้")
            continue
        med = float(df["close"].median())
        print(f"  + {name:38} {len(df):>7,} แท่ง  median {med:>10,.2f}")
        parts.append(df)
        sources.append(name)

    db_df = _load_db_prices(symbol)
    if db_df is not None:
        print(
            f"  + {'data/bot.db (' + symbol + ')':38} {len(db_df):>7,}  แท่ง"
            f"  median {db_df['close'].median():>10,.2f}"
        )
        parts.append(db_df)
        sources.append("data/bot.db")

    result = {"mixed_series": False, "jumps": [], "sources": sources}
    if len(parts) < 2:
        print("  (ข้อมูลไม่พอจะตรวจ)")
        return result

    meds = sorted(float(p["close"].median()) for p in parts)
    if meds[-1] / max(meds[0], 1e-9) >= 1.5:
        result["mixed_series"] = True
        print(
            f"\n  🔴 พบระดับราคาต่างกันมากในชุดเดียว: ต่ำสุด {meds[0]:,.2f}"
            f" → สูงสุด {meds[-1]:,.2f} (ต่าง {meds[-1] / meds[0]:.1f}×)"
        )
        print("     = มีโอกาสสูงที่จะเป็นคนละ symbol ปนกัน")

    merged = pd.concat(parts).sort_index()
    merged = merged[~merged.index.duplicated(keep="last")]
    pct = merged["close"].pct_change().abs()
    jumps = pct[pct > 0.20].sort_values(ascending=False).head(5)
    if len(jumps):
        print(f"\n  🔴 price jump > 20% ภายในแท่งถัดไป: {len(jumps)} จุด (โชว์ 5 อันดับ)")
        for ts, val in jumps.items():
            prev = merged["close"].shift(1).loc[ts]
            now = merged["close"].loc[ts]
            print(f"     {_fmt_ts(ts)}  {prev:>10,.2f} → {now:>10,.2f}  ({val * 100:>6.1f}%)")
            result["jumps"].append(
                {"ts": str(ts), "from": float(prev), "to": float(now), "pct": float(val)}
            )
        first_jump = min(jumps.index)
        tail = int((merged.index >= first_jump).sum())
        print(
            f"     ↳ หลังจุดกระโดดครั้งแรกมี {tail:,} แท่ง"
            f" ({tail / len(merged) * 100:.1f}% ของชุด) ที่ feature เพี้ยน"
        )
        result["tail_rows"] = tail
    else:
        print("\n  ✅ ไม่พบ price jump > 20% — ระดับราคาต่อเนื่อง")
    result["merged_rows"] = len(merged)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# 3) สร้างชุดข้อมูลสะอาด + Purged Walk-Forward
# ──────────────────────────────────────────────────────────────────────────────
def build_clean_dataset(symbol: str, tf_seconds: int) -> tuple[pd.DataFrame, list[str]]:
    """รวมเฉพาะไฟล์ symbol เดียวกัน (granularity ตรงหรือเล็กกว่า) + DB → timeframe เป้าหมาย"""
    parts: list[pd.DataFrame] = []
    used: list[str] = []
    for path in sorted(DATA_DIR.glob(f"deriv_{symbol}_*.csv")) + sorted(
        ROOT.glob(f"deriv_{symbol}_*.csv")
    ):
        gran = _granularity_seconds(path)
        if gran is None or gran > tf_seconds:
            continue
        df = _read_price_csv(path)
        if df is None:
            continue
        if gran < tf_seconds:
            df = _resample(df, f"{tf_seconds // 60}min")
        parts.append(df)
        used.append(path.name)

    db_df = _load_db_prices(symbol)
    if db_df is not None:
        parts.append(_resample(db_df, f"{tf_seconds // 60}min"))
        used.append("data/bot.db")

    if not parts:
        return pd.DataFrame(), used
    merged = pd.concat(parts).sort_index()
    merged = merged[~merged.index.duplicated(keep="last")]
    merged.index.name = "datetime"
    return merged, used


def purged_walkforward(
    X: pd.DataFrame,
    y: pd.Series,
    folds: int,
    embargo: int,
    n_estimators: int,
) -> list[dict]:
    n = len(X)
    edges = np.linspace(0, n, folds + 1, dtype=int)
    fold_rows: list[dict] = []
    for k in range(1, folds):
        test_start, test_end = int(edges[k]), int(edges[k + 1])
        train_end = test_start - embargo
        if test_end - test_start < 20 or train_end < 300:
            continue
        x_tr, y_tr = X.iloc[:train_end], y.iloc[:train_end]
        x_te, y_te = X.iloc[test_start:test_end], y.iloc[test_start:test_end]
        if y_tr.nunique() < 2 or y_te.nunique() < 2:
            continue
        model = _make_model(n_estimators)
        model.fit(x_tr, y_tr)
        proba = model.predict_proba(x_te)[:, 1]
        fold_rows.append(
            {
                "fold": k,
                "train_rows": int(len(x_tr)),
                "test_rows": int(len(x_te)),
                "test_start": str(x_te.index.min()),
                "test_end": str(x_te.index.max()),
                "auc": float(roc_auc_score(y_te, proba)),
                "logloss": float(log_loss(y_te, proba)),
                "brier": float(brier_score_loss(y_te, proba)),
                "proba": proba,
                "y": y_te.to_numpy(),
            }
        )
    return fold_rows


def section_cv(
    symbol: str, tf: str, horizon: int, deadzone: float, folds: int, n_estimators: int
) -> tuple[list[dict], int]:
    tf_seconds = TF_SECONDS[tf]
    print("\n" + "=" * 78)
    print(f"3) Purged Walk-Forward บนข้อมูลสะอาด ({symbol} / {tf} / horizon {horizon})")
    print("=" * 78)
    df, used = build_clean_dataset(symbol, tf_seconds)
    if df.empty:
        print("  ❌ ไม่พบข้อมูลของ symbol นี้")
        return [], 0
    print(f"  แหล่งข้อมูล: {', '.join(used)}")
    print(f"  หลัง merge: {len(df):,} แท่ง | {_fmt_ts(df.index.min())} → {_fmt_ts(df.index.max())}")
    gaps = df.index.to_series().diff().dt.total_seconds().dropna()
    if len(gaps):
        print(f"  ช่องว่าง: median {gaps.median() / 60:.0f} นาที | สูงสุด {gaps.max() / 3600:.1f} ชม.")

    X, y = build_dataset_v2(
        df, horizon=horizon, deadzone_atr_mult=deadzone, feature_columns=FEATURE_COLUMNS_V2
    )
    print(
        f"  หลังทำ label (deadzone {deadzone:g}×ATR): {len(X):,} แถว"
        f" | CALL {int((y == 1).sum()):,} / PUT {int((y == 0).sum()):,}"
    )
    if len(X) < 500:
        print("  ⚠️  ข้อมูลน้อยเกินกว่าจะสรุปผล (ควรมีอย่างน้อยหลายพันแถว)")

    print(f"  embargo = {horizon} แถว (กัน label ทับกัน), folds = {folds}")
    rows = purged_walkforward(X, y, folds, embargo=horizon, n_estimators=n_estimators)
    if not rows:
        print("  ❌ ไม่มี fold ที่ประเมินได้")
        return [], len(X)

    print(
        f"\n  {'fold':>4} {'train':>8} {'test':>7} {'ช่วง test':>33}"
        f" {'AUC':>7} {'logloss':>8} {'Brier':>7}"
    )
    for r in rows:
        span = f"{_fmt_ts(r['test_start'])} → {_fmt_ts(r['test_end'])}"
        print(
            f"  {r['fold']:>4} {r['train_rows']:>8,} {r['test_rows']:>7,} {span:>33}"
            f" {r['auc']:>7.4f} {r['logloss']:>8.4f} {r['brier']:>7.4f}"
        )
    aucs = [r["auc"] for r in rows]
    print(
        f"\n  สรุป: AUC เฉลี่ย {np.mean(aucs):.4f} ± {np.std(aucs):.4f}"
        f" (min {min(aucs):.4f} / max {max(aucs):.4f})"
    )
    print("  เกณฑ์อ่านค่า: 0.50 = เดาสุ่ม · 0.55 = พอใช้ · 0.60+ = ดี")
    return rows, len(X)


# ──────────────────────────────────────────────────────────────────────────────
# 4) Winrate vs threshold + Wilson CI
# ──────────────────────────────────────────────────────────────────────────────
def section_winrate(rows: list[dict], payout: float, deadzone: float) -> list[dict]:
    print("\n" + "=" * 78)
    print(f"4) Winrate vs confidence threshold (payout {payout:g})")
    print("=" * 78)
    if not rows:
        print("  (ข้าม — ไม่มีผลจาก CV)")
        return []
    proba = np.concatenate([r["proba"] for r in rows])
    labels = np.concatenate([r["y"] for r in rows])
    breakeven = 1 / (1 + payout)
    print(
        f"  breakeven = {breakeven * 100:.2f}% | ทดสอบบน {len(labels):,} แท่ง"
        f" (เฉพาะแท่งที่เคลื่อนเกิน {deadzone:g}×ATR)"
    )
    print(
        f"\n  {'conf':>5} {'ไม้':>6} {'ชนะ':>5} {'แพ้':>5} {'WR':>7}"
        f" {'95% CI':>17} {'net units':>10} {'coverage':>9}"
    )
    table: list[dict] = []
    for conf in [0.50, 0.52, 0.54, 0.55, 0.58, 0.60, 0.62, 0.65, 0.68, 0.70]:
        is_call = proba >= conf
        is_put = (1 - proba) >= conf
        traded = is_call | is_put
        n = int(traded.sum())
        if n == 0:
            continue
        wins = int(((is_call & (labels == 1)) | (is_put & (labels == 0))).sum())
        losses = n - wins
        wr = wins / n
        lo, hi = wilson_ci(wins, n)
        net = wins * payout - losses
        table.append(
            {
                "conf": conf,
                "n": n,
                "wins": wins,
                "losses": losses,
                "winrate_pct": round(wr * 100, 2),
                "ci_low_pct": round(lo * 100, 2),
                "ci_high_pct": round(hi * 100, 2),
                "net_units": round(net, 1),
                "coverage_pct": round(n / len(labels) * 100, 2),
            }
        )
        print(
            f"  {conf:>5.2f} {n:>6,} {wins:>5,} {losses:>5,} {wr * 100:>6.2f}%"
            f" {lo * 100:>7.2f}–{hi * 100:<6.2f}% {net:>+10.1f} {n / len(labels) * 100:>8.2f}%"
        )
    print("\n  ⚠️  ข้อควรระวัง: WR สูงที่จำนวนไม้น้อย = ยังพิสูจน์ไม่ได้ — ต้องดู CI ล่างและจำนวนไม้ควบคู่กัน")
    return table


# ──────────────────────────────────────────────────────────────────────────────
# 5) จำนวนไม้ที่ต้องเก็บ
# ──────────────────────────────────────────────────────────────────────────────
def section_samplesize(payout: float, target_wr: float = 0.70, z: float = 1.96) -> None:
    print("\n" + "=" * 78)
    print(f"5) ต้องเก็บกี่ไม้ถึงจะ 'พิสูจน์' ได้ว่า winrate {target_wr * 100:.0f}% จริง")
    print("=" * 78)
    breakeven = 1 / (1 + payout)

    def n_for_lower_bound(p: float, floor: float) -> int:
        for n in range(10, 1_000_001):
            if p - z * math.sqrt(p * (1 - p) / n) > floor:
                return n
        return -1

    n_above_be = n_for_lower_bound(target_wr, breakeven)
    n_above_60 = n_for_lower_bound(target_wr, 0.60)
    print(f"  payout {payout:g} → breakeven {breakeven * 100:.2f}%")
    print(f"  • พิสูจน์ว่า 'ดีกว่า breakeven' (CI ล่าง > {breakeven * 100:.1f}%): ≥ {n_above_be} ไม้")
    print(f"  • พิสูจน์ว่า 'ดีกว่า 60%' (CI ล่าง > 60%): ≥ {n_above_60} ไม้")
    print("\n  ถ้า WR จริง 70% ความกว้างของ CI ตามจำนวนไม้:")
    for n in (30, 50, 100, 200, 300, 500):
        se = math.sqrt(target_wr * (1 - target_wr) / n)
        print(
            f"    n={n:<4} → 95% CI {max(0, target_wr - z * se) * 100:5.1f}%"
            f" – {min(1, target_wr + z * se) * 100:5.1f}%"
        )
    print(f"\n  EV ต่อไม้ที่ WR 70% = {target_wr * payout - (1 - target_wr):+.3f} × เงินเดิมพัน")


# ──────────────────────────────────────────────────────────────────────────────
# 6) ประเมินโมเดล production บน holdout (optional)
# ──────────────────────────────────────────────────────────────────────────────
def section_production(
    rows: list[dict], symbol: str, tf: str, horizon: int, deadzone: float, payout: float
) -> dict | None:
    if not rows:
        return None
    model_name = {"M1": "model_m1.joblib", "M5": "model_m5.joblib"}.get(tf)
    if model_name is None:
        return None
    path = PIPELINE / model_name
    if not path.exists():
        return None
    import joblib

    bundle = joblib.load(path)
    feats = list(bundle.get("features") or [])
    if len(feats) != len(FEATURE_COLUMNS_V2):
        print(f"\n  ⚠️  {model_name} ใช้ {len(feats)} features (ชุดปัจจุบัน {len(FEATURE_COLUMNS_V2)})")
        return None
    if int(bundle.get("horizon", horizon)) != horizon:
        print(
            f"  ⚠️  horizon ของโมเดล ({bundle.get('horizon')}) ไม่ตรงกับที่ทดสอบ ({horizon})"
            " — ข้ามการประเมิน production"
        )
        return None

    df, _ = build_clean_dataset(symbol, TF_SECONDS[tf])
    if df.empty:
        return None
    X, y = build_dataset_v2(
        df, horizon=horizon, deadzone_atr_mult=deadzone, feature_columns=FEATURE_COLUMNS_V2
    )
    cut = int(len(X) * 0.8)
    x_te, y_te = X.iloc[cut:], y.iloc[cut:]
    if len(x_te) < 50 or y_te.nunique() < 2:
        return None
    model = bundle["model"]
    proba = model.predict_proba(x_te[feats])[:, 1]
    auc = float(roc_auc_score(y_te, proba))
    print("\n" + "=" * 78)
    print(f"6) โมเดล production ({model_name}, version {bundle.get('version')}) บน 20% ท้าย")
    print("=" * 78)
    print(
        f"  อ้างอิงตอนเทรน: n={bundle.get('n_rows'):,} auc_val={bundle.get('auc_val')}"
        f" auc_test={bundle.get('auc_test')} conf={bundle.get('chosen_conf')}"
    )
    print(f"  บนข้อมูลปัจจุบัน: n={len(x_te):,} AUC={auc:.4f}")
    best = None
    for conf in (bundle.get("chosen_conf") or 0.52, 0.53, 0.55, 0.60, 0.65):
        is_call = proba >= conf
        is_put = (1 - proba) >= conf
        n = int((is_call | is_put).sum())
        if n == 0:
            continue
        wins = int(((is_call & (y_te.to_numpy() == 1)) | (is_put & (y_te.to_numpy() == 0))).sum())
        wr = wins / n
        lo, hi = wilson_ci(wins, n)
        net = wins * payout - (n - wins)
        print(
            f"   conf {conf:.2f}: n={n:,} WR={wr * 100:.2f}% CI {lo * 100:.1f}–{hi * 100:.1f}%"
            f" net={net:+.1f}"
        )
        if best is None or net > best["net_units"]:
            best = {
                "conf": conf,
                "n": n,
                "winrate_pct": round(wr * 100, 2),
                "net_units": round(net, 1),
            }
    print("\n  ⚠️  หมายเหตุ: โมเดลถูกเทรนบนข้อมูลที่อาจทับช่วงนี้ → ไม่ใช่ OOS ที่สะอาด 100%")
    return {"model": model_name, "auc": round(auc, 4), "best": best}


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="ตรวจสุขภาพข้อมูลเทรน + ประเมินโมเดล ML (read-only)")
    parser.add_argument("--symbol", default="frxXAUUSD")
    parser.add_argument("--tf", default="M5", choices=sorted(TF_SECONDS))
    parser.add_argument("--horizon", type=int, default=0, help="0 = อัตโนมัติตาม tf")
    parser.add_argument("--deadzone", type=float, default=0.25)
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--estimators", type=int, default=200)
    parser.add_argument("--payout", type=float, default=0.82)
    parser.add_argument("--skip-cv", action="store_true")
    parser.add_argument("--json", default="", help="บันทึกผลเป็น JSON ที่ path นี้")
    args = parser.parse_args()

    horizon = args.horizon or (15 if args.tf == "M1" else 6)
    print("=" * 78)
    print("ML AUDIT — read-only (ไม่เขียน DB / ไม่บันทึกโมเดล)")
    print(f"symbol={args.symbol} tf={args.tf} horizon={horizon} deadzone={args.deadzone:g}")
    print("=" * 78)

    files = section_scan(args.symbol)
    contamination = section_contamination(args.symbol)

    report: dict = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "symbol": args.symbol,
        "tf": args.tf,
        "horizon": horizon,
        "deadzone": args.deadzone,
        "files": [
            {
                "path": str(f.path.relative_to(ROOT))
                if f.path.is_relative_to(ROOT)
                else str(f.path),
                "rows": f.rows,
                "start": str(f.start),
                "end": str(f.end),
                "close_median": round(f.close_median, 2),
                "median_gap_min": f.median_gap_min,
                "max_gap_hours": f.max_gap_hours,
            }
            for f in files
        ],
        "contamination": {k: v for k, v in contamination.items() if k != "sources"},
        "cv": [],
        "winrate": [],
        "production": None,
    }

    rows: list[dict] = []
    if not args.skip_cv:
        rows, n_rows = section_cv(
            args.symbol, args.tf, horizon, args.deadzone, args.folds, args.estimators
        )
        report["dataset_rows"] = n_rows
        report["cv"] = [{k: v for k, v in r.items() if k not in ("proba", "y")} for r in rows]
        report["winrate"] = section_winrate(rows, args.payout, args.deadzone)
        if rows:
            report["auc_mean"] = round(float(np.mean([r["auc"] for r in rows])), 4)

    section_samplesize(args.payout)
    report["production"] = section_production(
        rows, args.symbol, args.tf, horizon, args.deadzone, args.payout
    )

    if args.json:
        out = Path(args.json)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nบันทึกผล JSON → {out}")

    print("\n" + "=" * 78)
    print("จบการตรวจ — ไฟล์นี้ไม่แก้ข้อมูลใด ๆ ทั้งสิ้น")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
