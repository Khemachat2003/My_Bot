"""
validate_gate_real.py — พิสูจน์ Regime-Gate ด้วยสัญญาณ FIRE จริง (ออก-ตัวอย่างตามเวลา)
=====================================================================================
- train gate model บน CSV 4 เดือน (ข้อมูล ≤ 7 ส.ค.) — เหมือน experimental walk-forward
- test: สัญญาณ FIRE จริงจาก VPS (14-15 ส.ค. มี WIN/LOSE จริง) + ราคา M5 สด + DXY สด (Yahoo)
- เปรียบ winrate: ยิงทุกสัญญาณ vs กรองด้วย gate ที่ threshold ต่างๆ
  → ถ้า "ที่เหลือ" ได้ ≥60% และ n ใหญ่พอ = หลักฐานจริงว่า gate ใช้ได้

รัน (ต้องมี .env: DASHBOARD_USER / DASHBOARD_PASS / MT5_VPS_API_URL):
    ./venv/Scripts/python.exe -m backend.ml_forecaster.validate_gate_real
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
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

from backend.ml_forecaster.features_regime import add_volatility_regime_features
from backend.ml_forecaster.features_v2 import SESSION_COLUMNS
from backend.ml_forecaster.regime_gate import (
    BASE_FEATURES, HORIZON, PAYOUT, TOUCH_TOL, add_ema200_features,
    add_macro_features, build_features_v2, load_csv, _make_model,
)

GATE_CONFS = [0.55, 0.58, 0.60, 0.62, 0.65]
MIN_SIG = 10


def _get_env(path: Path) -> dict:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def fetch_vps(env: dict, path: str, params: dict | None = None) -> list:
    base = env.get("MT5_VPS_API_URL", "http://207.148.123.201:8000").rstrip("/")
    url = f"{base}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    user = env.get("MT5_API_USER") or env.get("DASHBOARD_USER") or "admin7717"
    pwd = env.get("MT5_API_PASS") or env.get("DASHBOARD_PASS") or "admin070717"
    token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}",
                                               "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_dxy_hourly(start_ts: int, end_ts: int) -> pd.Series:
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
           f"?interval=1h&period1={start_ts}&period2={end_ts}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))["chart"]["result"][0]
    ts = data["timestamp"]
    close = data["indicators"]["quote"][0]["close"]
    s = pd.Series(close, index=pd.to_datetime(ts, unit="s", utc=True))
    return s.dropna()


def build_gate_training(csv_path: Path, macro_path: Path | None) -> tuple[pd.DataFrame, list[str]]:
    df_tf = load_csv(csv_path)
    macro = load_csv(macro_path) if macro_path and macro_path.exists() else None
    from backend.ml_forecaster.regime_gate import build_dataset
    feat, cols = build_dataset(df_tf, macro)
    cand = feat[feat["_cand"] == 1].dropna(subset=["_target"])
    return cand, cols


def score_real_signals(cand: pd.DataFrame, cols: list[str], model, sigs: list[dict],
                       candles: pd.DataFrame, dxy: pd.Series) -> list[dict]:
    """คำนวณ P(win) ของสัญญาณจริงที่ timestamp นั้น (ไม่มี lookahead — ใช้ข้อมูลก่อนเข้าออเดอร์)"""
    # เตรียม feature frame จากแท่ง M5 สด + dxy
    feat = build_features_v2(candles.copy())
    feat = add_volatility_regime_features(feat)
    feat = add_ema200_features(feat)
    # slope columns ที่ regime_gate สร้าง — สร้างใหม่เหมือนกัน
    e200 = feat["close"].ewm(span=200, adjust=False).mean()
    feat["ema200_slope_48"] = (e200 - e200.shift(48)) / e200.shift(48) * 100.0
    feat["adx_slope"] = feat["adx"] - feat["adx"].shift(12)
    macro = dxy.to_frame().rename(columns={0: "close"})
    feat = add_macro_features(feat, macro)

    medians = cand[cols].median()
    results = []
    for s in sigs:
        try:
            t = pd.Timestamp(s["signal_time"])
            if t.tzinfo is None:
                t = t.tz_localize("utc")
            else:
                t = t.tz_convert("utc")
        except Exception:
            continue
        past = feat[feat.index < t]
        if past.empty:
            continue
        row = past.iloc[-1]
        X = pd.DataFrame([row[cols]], columns=cols)
        X = X.fillna(medians)
        p = float(model.predict_proba(X)[:, 1][0])
        direction = str(s.get("direction", "")).upper()
        result = str(s.get("result", "PENDING")).upper()
        results.append({
            "signal_time": str(t), "direction": direction, "result": result,
            "prob_win": round(p, 4), "entry": s.get("entry_price"),
        })
    return results


def main():
    env = _get_env(ROOT / ".env")
    local_csv = ROOT / "data" / "deriv_frxXAUUSD_300s_120d.csv"
    macro_csv = ROOT / "data" / "macro_dxy_60m.csv"

    cand, cols = build_gate_training(local_csv, macro_csv)
    if cand.empty:
        sys.exit("ไม่มี candidate ใน train")
    print(f"train candidates: {len(cand)} | features: {len(cols)} | "
          f"baseline winrate={cand['_target'].mean() * 100:.2f}%")

    # ── train gate model บนข้อมูลทั้งหมด (≤ 7 ส.ค.) ──
    X_all, y_all = cand[cols], cand["_target"]
    model = _make_model()
    model.fit(X_all, y_all)
    print(f"model trained ถึง {cand.index[-1]}")

    # ── ดึงข้อมูลสด ──
    print("fetch VPS signals + prices ...")
    sigs = fetch_vps(env, "/api/signals", {"limit": 1000})
    prices = fetch_vps(env, "/api/prices", {"limit": 5000, "symbol": "frxXAUUSD"})
    if not prices:
        sys.exit("ไม่มี prices จาก VPS")
    pf = pd.DataFrame(prices)
    pf = pf.rename(columns={c: c.lower() for c in pf.columns})
    pf["ts"] = pd.to_datetime(pf["ts"], utc=True)
    pf = pf.set_index("ts")[["open", "high", "low", "close"]].sort_index()
    o = pf["open"].resample("5min", closed="left", label="left", origin="epoch").first()
    h = pf["high"].resample("5min", closed="left", label="left", origin="epoch").max()
    l = pf["low"].resample("5min", closed="left", label="left", origin="epoch").min()
    c = pf["close"].resample("5min", closed="left", label="left", origin="epoch").last()
    candles = pd.concat([o, h, l, c], axis=1).dropna()
    candles["volume"] = 0.0
    candles = candles[["open", "high", "low", "close", "volume"]]
    candles.index.name = "datetime"
    print(f"แท่ง M5 สด: {len(candles)} ({candles.index[0]} → {candles.index[-1]})")

    end_ts = int(time.time())
    start_ts = int((candles.index[0] - pd.Timedelta("1d")).timestamp())
    print(f"fetch DXY hourly {start_ts}..{end_ts} ...")
    dxy = fetch_dxy_hourly(start_ts, end_ts)
    print(f"DXY rows: {len(dxy)} ({dxy.index[0]} → {dxy.index[-1]})")

    # ── กรองสัญญาณ M5 ที่มีผลแล้ว ──
    def _utc(s):
        t = pd.Timestamp(s)
        return t if t.tzinfo is not None else t.tz_localize("utc")
    sigs_m5 = [s for s in sigs if str(s.get("timeframe", "")).upper() in ("M5", "5M")
               and s.get("result") in ("WIN", "LOSE")
               and _utc(s["signal_time"]) > candles.index[0]]
    print(f"สัญญาณ FIRE M5 มีผล: {len(sigs_m5)}")

    scored = score_real_signals(cand, cols, model, sigs_m5, candles, dxy)
    if len(scored) < 3:
        print("สัญญาณที่เข้ากรอบน้อยเกินไป — ลอง ไม่กรอง timeframe/ผล ดู:")
        sigs_all = [s for s in sigs if s.get("result") in ("WIN", "LOSE")]
        scored = score_real_signals(cand, cols, model, sigs_all, candles, dxy)
        print(f"  สัญญาณทั้งหมดมีผล: {len(scored)}")

    if not scored:
        sys.exit("ไม่มีสัญญาณพอจะประเมิน")

    df = pd.DataFrame(scored)
    # label ถูก-ผิดของ gate: ทิศทางตรงกับที่ระบบพยากรณ์ (gate รู้ทิศจาก ema_align)
    print("\n" + "=" * 70)
    print("  VALIDATION สัญญาณจริง (out-of-sample) — ยิงทุกตัว vs ผ่าน gate")
    print("=" * 70)
    for label, sub in [("CALL", df[df["direction"] == "CALL"]),
                       ("PUT", df[df["direction"] == "PUT"]), ("ทั้งหมด", df)]:
        if len(sub):
            print(f"  {label:<6} n={len(sub):>3} winrate={ (sub['result']=='WIN').mean()*100:.1f}%")

    base_wr = (df["result"] == "WIN").mean() * 100
    base_n = len(df)
    print(f"\n  ยิงทุกสัญญาณ: n={base_n}  winrate={base_wr:.1f}%")
    print(f"  {'Gate conf':>10} | {'n ที่เหลือ':>9} | {'Winrate':>8} | ผ่าน 60%?")
    for c in GATE_CONFS:
        keep = df[df["prob_win"] >= c]
        if len(keep) == 0:
            print(f"  {c:>10.2f} | {0:>9} | {'-':>8}")
            continue
        wr = (keep["result"] == "WIN").mean() * 100
        ok = "✅" if (len(keep) >= MIN_SIG and wr >= 60.0) else ""
        print(f"  {c:>10.2f} | {len(keep):>9} | {wr:>7.1f}% {ok}")
    df.to_csv(ROOT / "data" / "gate_real_validation.csv", index=False,
              encoding="utf-8")
    print(f"\n  บันทึกรายละเอียด: data/gate_real_validation.csv")


if __name__ == "__main__":
    main()
