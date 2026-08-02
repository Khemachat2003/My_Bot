"""
setup_scorer.py — 🔵 Sniper Reversion Checklist V2 (Rule-Based Setup Engine)
===================================================================================
ปรับตามเทคนิคที่เจ้าของระบบใช้เทรด option จริง (อธิบายโดยเจ้าของ):

  Flow จริง: ดูราคา → ดูเทรน (ZigZag/EMA) → ADX แรงไหม → RSI over/divergence
             → EMA 3 เส้นตัดกันตามเทรนไหม → BB บีบ/ขยาย/ตำแหน่งเทียบ SMA
             → ZigZag ทำ HH/HL ตามเทรน → ราคาออกนอก BB → ราคาใกล้ EMA200/100
             → จุดนั้นอยู่ในแนวรับ/แนวต้านหลักหรือย่อย + grip ไหม
             → สุดท้าย: rejection ที่โซน EMA → เข้า

  11 ข้อ ถ่วงน้ำหนัก (max = 15) ตั้งค่าได้ใน setup_config.json (ไม่ต้องแตะโค้ด)
  ค่า config โหลดอัตโนมัติใหม่ทุกครั้งที่ไฟล์เปลี่ยน (mtime) — ระบบ poll 15 วิ

  Tier สัญญาณ (กันพลาดจังหวะตามที่เจ้าของระบบกังวล):
    FIRE  = setup ครบ + ราคากลับมาที่ EMA + มี rejection → พิจารณาเข้า
    FADE  = RSI สุดขั้ว + ราคายืดไกลเกินไป (ไม่ต้องรอราคากลับถึง EMA) → เข้าเร็ว
    WATCH = ราคากลับมาอยู่ในโซน EMA แล้ว รอ rejection ยืนยัน (เตรียมแผน)
    NONE  = ยังไม่เข้าเงื่อนไข
"""
from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

CONFIG_PATH = Path(__file__).resolve().parent / "setup_config.json"
_config_cache: dict = {"mtime": 0.0, "data": None}


def load_config() -> dict:
    """โหลด config แบบ cache ตาม mtime → แก้ไฟล์แล้วเห็นผลทันที"""
    try:
        mtime = os.stat(CONFIG_PATH).st_mtime
        if _config_cache["data"] is not None and _config_cache["mtime"] == mtime:
            return _config_cache["data"]
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        _config_cache.update(mtime=mtime, data=cfg)
        return cfg
    except Exception:
        return _config_cache["data"] or {}


@dataclass
class SetupResult:
    timeframe: str
    target_hold_minutes: int
    score: float = 0.0
    max_score: int = 15
    tier: str = "NONE"                       # FIRE / FADE / WATCH / NONE
    direction: str = ""                      # CALL / PUT
    bias: str = ""                           # BULLISH_REVERSION / BEARISH_REVERSION
    entry_trigger: bool = False              # True ถ้า tier เป็น FIRE หรือ FADE (เข้าได้)
    entry_trigger_note: str = ""
    details: dict[str, dict] = field(default_factory=dict)  # name -> {ok, frac, note, weight}
    grip_hits: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)
    model_prob: float | None = None


# ── ตัวชี้วัดพื้นฐาน ──────────────────────────────────────────────────────────
def _calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _calc_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _calc_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    width_pct = (upper - lower) / sma * 100.0
    return sma, upper, lower, width_pct


def _calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


# ── Swing Pivot (Fractal) ─────────────────────────────────────────────────────
def _find_pivots(high: pd.Series, low: pd.Series, left: int = 2, right: int = 2):
    n = len(high)
    piv_highs: list[tuple[int, float]] = []
    piv_lows: list[tuple[int, float]] = []
    for i in range(left, n - right):
        window_h = high.iloc[i - left: i + right + 1]
        if high.iloc[i] == window_h.max() and window_h.max() > window_h.min():
            piv_highs.append((i, float(high.iloc[i])))
        window_l = low.iloc[i - left: i + right + 1]
        if low.iloc[i] == window_l.min() and window_l.max() > window_l.min():
            piv_lows.append((i, float(low.iloc[i])))
    return piv_highs, piv_lows


def _zigzag_structure(piv_highs, piv_lows) -> str:
    if len(piv_highs) >= 2 and piv_highs[-1][1] > piv_highs[-2][1]:
        hh = True
    elif len(piv_highs) >= 2:
        hh = False
    else:
        hh = None
    if len(piv_lows) >= 2 and piv_lows[-1][1] > piv_lows[-2][1]:
        hl = True
    elif len(piv_lows) >= 2:
        hl = False
    else:
        hl = None
    if hh and hl:
        return "UPTREND"
    if hh is False and hl is False:
        return "DOWNTREND"
    return "SIDEWAYS"


# ── แนวรับ/แนวต้าน หลัก/ย่อย (cluster pivot + นับครั้งเทสต์ + โซน) ───────────
def _cluster_levels(prices: list[float], tol_pct: float) -> list[dict]:
    """รวม pivot ที่ใกล้กัน (ภายใน tolerance) เป็น 1 แนว → นับครั้งที่เทสต์"""
    if not prices:
        return []
    clusters: list[list[float]] = []
    for p in sorted(prices):
        if not clusters:
            clusters.append([p])
            continue
        ref = statistics.median(clusters[-1])
        if abs(p - ref) <= ref * tol_pct / 100.0:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    out = []
    for c in clusters:
        out.append({
            "price": statistics.median(c),
            "tests": len(c),
            "span": max(c) - min(c),
        })
    return out


def _find_levels(df: pd.DataFrame, cfg: dict, lookback: int = 200) -> tuple[list[dict], list[dict]]:
    """คืน (supports, resistances) ที่ถ่วงด้วยจำนวนครั้งที่เทสต์"""
    sl = min(lookback, len(df))
    seg = df.iloc[-sl:]
    piv_h, piv_l = _find_pivots(seg["high"], seg["low"], left=2, right=2)
    tol = cfg.get("sr", {}).get("tolerance_pct", 0.20)
    supports = _cluster_levels([p for _, p in piv_l], tol)
    resistances = _cluster_levels([p for _, p in piv_h], tol)
    return supports, resistances


def _nearest_level(price: float, levels: list[dict]) -> dict | None:
    if not levels:
        return None
    best = None
    best_dist = math.inf
    for lv in levels:
        d = abs(price - lv["price"])
        if d < best_dist:
            best_dist = d
            best = lv
    if best is None:
        return None
    return {**best, "dist": best_dist, "dist_pct": best_dist / price * 100.0}


# ── Grip (เส้นเลขกลม) แบบ scale ตามราคาอัตโนมัติ ──────────────────────────────
def _nice_step(v: float) -> float:
    if v <= 0:
        return 1.0
    exp = math.floor(math.log10(v))
    base = v / 10 ** exp
    if base < 1.5:
        return 1 * 10 ** exp
    if base < 3.5:
        return 2 * 10 ** exp
    if base < 7.5:
        return 5 * 10 ** exp
    return 10 * 10 ** exp


def _grip_step(price: float, cfg: dict) -> float:
    g = cfg.get("grip", {})
    if g.get("auto_scale", True):
        return _nice_step(price / g.get("scale_divisor", 800))
    return g.get("fixed_step", 5.0)


def _near_grip(price: float, step: float, tol_pct: float) -> bool:
    line = round(price / step) * step
    return abs(price - line) / price * 100.0 <= tol_pct


# ── RSI Divergence / Convergence ─────────────────────────────────────────────
def _divergence_frac(rsi: pd.Series, piv_lows, piv_highs, direction: str) -> tuple[float, str]:
    if direction == "CALL":
        if len(piv_lows) >= 2:
            (i1, p1), (i2, p2) = piv_lows[-2], piv_lows[-1]
            r1, r2 = rsi.iloc[i1], rsi.iloc[i2]
            if p2 < p1 and r2 > r1:
                return 1.0, f"Bullish Divergence: ราคา {p1:.2f}→{p2:.2f} (LL) แต่ RSI {r1:.1f}→{r2:.1f} (HL)"
            if p2 <= p1 * 1.003 and r2 > r1:
                return 0.7, f"Bullish Convergence: ราคา {p1:.2f}→{p2:.2f} (สมดุล) แต่ RSI {r1:.1f}→{r2:.1f} (สูงขึ้น)"
        r_now, r_prev = rsi.iloc[-1], rsi.iloc[-3]
        if r_now > r_prev and r_now < 45:
            return 0.5, f"RSI เริ่มพลิกกลับ {r_prev:.1f}→{r_now:.1f} (จาก oversold)"
        return 0.0, "ไม่พบ Bullish Divergence/Convergence"
    else:
        if len(piv_highs) >= 2:
            (i1, p1), (i2, p2) = piv_highs[-2], piv_highs[-1]
            r1, r2 = rsi.iloc[i1], rsi.iloc[i2]
            if p2 > p1 and r2 < r1:
                return 1.0, f"Bearish Divergence: ราคา {p1:.2f}→{p2:.2f} (HH) แต่ RSI {r1:.1f}→{r2:.1f} (LH)"
            if p2 >= p1 * 0.997 and r2 < r1:
                return 0.7, f"Bearish Convergence: ราคา {p1:.2f}→{p2:.2f} (สมดุล) แต่ RSI {r1:.1f}→{r2:.1f} (ต่ำลง)"
        r_now, r_prev = rsi.iloc[-1], rsi.iloc[-3]
        if r_now < r_prev and r_now > 55:
            return 0.5, f"RSI เริ่มพลิกกลับ {r_prev:.1f}→{r_now:.1f} (จาก overbought)"
        return 0.0, "ไม่พบ Bearish Divergence/Convergence"


# ── Rejection Candle (ดูย้อนหลัง lookback แท่ง, แบบมี partial) ────────────────
def _rejection_frac(df: pd.DataFrame, direction: str, lookback: int = 2) -> tuple[float, str]:
    n = len(df)
    best = 0.0
    best_note = ""
    for k in range(1, lookback + 1):
        idx = n - k
        if idx < 1:
            break
        cur = df.iloc[idx]
        prev = df.iloc[idx - 1]
        body = abs(cur["close"] - cur["open"])
        rng = max(cur["high"] - cur["low"], 1e-9)
        upper_w = cur["high"] - max(cur["close"], cur["open"])
        lower_w = min(cur["close"], cur["open"]) - cur["low"]
        doji = body / rng <= 0.12
        if direction == "CALL":
            if (cur["close"] > cur["open"] and prev["close"] < prev["open"]
                    and cur["close"] >= prev["open"] and cur["open"] <= prev["close"]):
                return 1.0, f"Bullish Engulfing (แท่งก่อน {k})"
            if lower_w >= body * 1.5 and lower_w > 0:
                if k == 1:
                    return 1.0, "Pinbar/Hammer ไส้ล่าง ≥1.5x (แท่งล่าสุด)"
                best = max(best, 0.6)
                best_note = f"Pinbar/Hammer ไส้ล่าง (แท่งก่อน {k})"
            if doji:
                if k == 1:
                    return 1.0, "Doji — rejection (แท่งล่าสุด)"
                best = max(best, 0.6)
                best_note = f"Doji (แท่งก่อน {k})"
        elif direction == "PUT":
            if (cur["close"] < cur["open"] and prev["close"] > prev["open"]
                    and cur["close"] <= prev["open"] and cur["open"] >= prev["close"]):
                return 1.0, f"Bearish Engulfing (แท่งก่อน {k})"
            if upper_w >= body * 1.5 and upper_w > 0:
                if k == 1:
                    return 1.0, "Shooting Star ไส้บน ≥1.5x (แท่งล่าสุด)"
                best = max(best, 0.6)
                best_note = f"Shooting Star ไส้บน (แท่งก่อน {k})"
            if doji:
                if k == 1:
                    return 1.0, "Doji — rejection (แท่งล่าสุด)"
                best = max(best, 0.6)
                best_note = f"Doji (แท่งก่อน {k})"
    if best > 0:
        return best, best_note
    return 0.0, f"ยังไม่เห็น Rejection ชัดเจนใน {lookback} แท่งย้อนหลัง"


# ── คะแนนรายทิศทาง ───────────────────────────────────────────────────────────
def _score_direction(df: pd.DataFrame, direction: str, ctx: dict, cfg: dict) -> tuple[float, dict, list[str]]:
    weights: dict = cfg.get("weights", {})
    details: dict[str, dict] = {}
    grip_hits: list[str] = []
    score = 0.0

    def add(name: str, frac: float, note: str):
        nonlocal score
        w = float(weights.get(name, 1))
        frac = max(0.0, min(1.0, frac))
        ok = frac >= 0.5
        details[name] = {"ok": ok, "frac": round(frac, 2), "note": note, "weight": int(w)}
        score += w * frac

    close = ctx["close"]
    last_close = close.iloc[-1]

    # 1) โครงสร้างเทรน (ZigZag) — HH/HL ตามทิศ CALL / LH/LL ตามทิศ PUT
    struct = ctx["structure"]
    piv_h, piv_l = ctx["piv_highs"], ctx["piv_lows"]
    if direction == "CALL":
        ok = struct in ("UPTREND", "SIDEWAYS") and len(piv_l) >= 2 and piv_l[-1][1] >= piv_l[-2][1]
        add("structure", 1.0 if ok else 0.0, f"โครงสร้างสวิง: {struct}" + ("" if ok else " (ขัดทิศ CALL)"))
    else:
        ok = struct in ("DOWNTREND", "SIDEWAYS") and len(piv_h) >= 2 and piv_h[-1][1] <= piv_h[-2][1]
        add("structure", 1.0 if ok else 0.0, f"โครงสร้างสวิง: {struct}" + ("" if ok else " (ขัดทิศ PUT)"))

    # 2) ADX — เทรนแข็งแรง
    adx = ctx["adx"]
    add("adx", 1.0 if adx >= cfg.get("adx_min", 20) else 0.0, f"ADX={adx:.1f} (>= {cfg.get('adx_min', 20)})")

    # 3) RSI Zone (มี partial ใกล้สุดขั้ว)
    rsi = float(ctx["rsi"].iloc[-1])
    rzone = float(cfg.get("rsi_zone", 30))
    if direction == "CALL":
        frac = 1.0 if rsi <= rzone else (0.5 if rsi <= rzone + 10 else 0.0)
        add("rsi_zone", frac, f"RSI={rsi:.1f} (<= {rzone:.0f})")
    else:
        frac = 1.0 if rsi >= 100 - rzone else (0.5 if rsi >= 100 - rzone - 10 else 0.0)
        add("rsi_zone", frac, f"RSI={rsi:.1f} (>= {100 - rzone:.0f})")

    # 4) RSI Divergence/Convergence
    dfrac, dnote = _divergence_frac(ctx["rsi"], piv_l, piv_h, direction)
    add("rsi_div", dfrac, dnote)

    # 5) EMA 50/100/200 — เทรน + สัญญาณตัดระยะกลาง
    ema50, ema100, ema200 = ctx["ema50"], ctx["ema100"], ctx["ema200"]
    if direction == "CALL":
        align = ema50.iloc[-1] <= ema100.iloc[-1] <= ema200.iloc[-1]      # ราคาอยู่ใต้ EMA = ยืดลงแล้ว
        crossed = ema50.iloc[-1] > ema100.iloc[-1] and ema50.iloc[-3] <= ema100.iloc[-3]
        ema_note = (f"EMA50={ema50.iloc[-1]:.2f} ≤ EMA100={ema100.iloc[-1]:.2f} ≤ EMA200={ema200.iloc[-1]:.2f}"
                    if align else f"EMA50 ตัดขึ้นเหนือ EMA100 แล้ว" if crossed else
                    f"EMA50={ema50.iloc[-1]:.2f} EMA100={ema100.iloc[-1]:.2f} EMA200={ema200.iloc[-1]:.2f}")
    else:
        align = ema50.iloc[-1] >= ema100.iloc[-1] >= ema200.iloc[-1]
        crossed = ema50.iloc[-1] < ema100.iloc[-1] and ema50.iloc[-3] >= ema100.iloc[-3]
        ema_note = (f"EMA50={ema50.iloc[-1]:.2f} ≥ EMA100={ema100.iloc[-1]:.2f} ≥ EMA200={ema200.iloc[-1]:.2f}"
                    if align else f"EMA50 ตัดลงใต้ EMA100 แล้ว" if crossed else
                    f"EMA50={ema50.iloc[-1]:.2f} EMA100={ema100.iloc[-1]:.2f} EMA200={ema200.iloc[-1]:.2f}")
    add("ema", min(1.0, (0.7 if align else 0.0) + (0.5 if crossed else 0.0)), ema_note)

    # 6) BB เต็มรูปแบบ — ตำแหน่งเทียบ mid + ทะลุ band + ขยาย/บีบ
    bb_mid, bb_up, bb_lo = ctx["bb_mid"], ctx["bb_up"], ctx["bb_lo"]
    width = ctx["bb_width"]
    cur_w = width.iloc[-1]
    avg_w = width.rolling(20).mean().iloc[-1]
    min_w30 = width.rolling(30).min().iloc[-1]
    expanding = bool(cur_w > avg_w)
    recent_squeeze = bool(width.iloc[-6:].min() <= min_w30 * 1.05) if not np.isnan(min_w30) else False
    if direction == "CALL":
        side = bool(last_close < bb_mid.iloc[-1])
        extreme = bool(last_close <= bb_lo.iloc[-1])
        pos_note = f"ราคา {last_close:.2f} ใต้ mid {bb_mid.iloc[-1]:.2f}" + (" ทะลุ band ล่าง!" if extreme else "")
    else:
        side = bool(last_close > bb_mid.iloc[-1])
        extreme = bool(last_close >= bb_up.iloc[-1])
        pos_note = f"ราคา {last_close:.2f} เหนือ mid {bb_mid.iloc[-1]:.2f}" + (" ทะลุ band บน!" if extreme else "")
    side_frac = 1.0 if extreme else (0.7 if side else 0.0)
    state_frac = 1.0 if expanding else (0.5 if recent_squeeze else 0.0)
    bb_note = f"{pos_note} | BB width {cur_w:.2f}% " + ("ขยาย" if expanding else ("กำลังบีบ" if recent_squeeze else "ทรงตัว"))
    add("bb", side_frac * 0.6 + state_frac * 0.4, bb_note)

    # 7) SMA5 — ระยะยืดเกิน + จุดตัดระยะสั้น
    sma5 = ctx["sma5"]
    atr = ctx["atr"]
    dist_atr = abs(last_close - sma5.iloc[-1]) / atr if atr else 0.0
    overext = dist_atr >= float(cfg.get("sma5_atr_min", 1.0))
    if direction == "CALL":
        crossed = last_close > sma5.iloc[-1] and close.iloc[-2] <= sma5.iloc[-2]
        cross_txt = "ตัดขึ้น" if crossed else ""
    else:
        crossed = last_close < sma5.iloc[-1] and close.iloc[-2] >= sma5.iloc[-2]
        cross_txt = "ตัดลง" if crossed else ""
    sma_note = f"ห่าง SMA5 {dist_atr:.2f}x ATR" + (f" + SMA5 {cross_txt}" if crossed else "")
    add("sma5", min(1.0, (0.5 if overext else 0.0) + (0.5 if crossed else 0.0)), sma_note)

    # 8) แนวรับ/แนวต้าน หลัก/ย่อย + grip เสริม
    sr = cfg.get("sr", {})
    tol = float(sr.get("tolerance_pct", 0.20))
    major_tests = int(sr.get("major_tests", 3))
    minor_tests = int(sr.get("minor_tests", 2))
    if direction == "CALL":
        near = _nearest_level(last_close, ctx["supports"])
        lvl_word = "แนวรับ"
    else:
        near = _nearest_level(last_close, ctx["resistances"])
        lvl_word = "แนวต้าน"
    grip_step = _grip_step(last_close, cfg)
    ng = _near_grip(last_close, grip_step, float(cfg.get("grip", {}).get("tolerance_pct", 0.05)))
    if near and near["dist_pct"] <= tol:
        tests = near["tests"]
        is_zone = near["span"] > last_close * float(sr.get("zone_pct", 0.35)) / 100.0
        if tests >= major_tests:
            frac = 1.0
            lvl_type = "แนวหลัก"
        elif tests >= minor_tests:
            frac = 0.7
            lvl_type = "แนวย่อย"
        else:
            frac = 0.5
            lvl_type = "โซนเบา"
        if is_zone:
            lvl_type += " (โซน)"
        if ng and tests >= minor_tests:
            frac = 1.0
            grip_hits.append("Grip")
        note = f"{lvl_type} {near['price']:.2f} เทสต์ {tests} ครั้ง ห่าง {near['dist_pct']:.2f}%"
        if ng:
            note += f" + Grip {round(last_close / grip_step) * grip_step:.2f}"
            grip_hits.append("Grip")
    else:
        frac = 0.0
        note = f"ไม่ใกล้{lvl_word}สำคัญ (tol {tol:.2f}%)" + (f" | Grip ห่าง" if ng else "")
    add("sr", frac, note)

    # 9) EMA Pullback — ราคากลับมาใกล้ EMA200/100
    tol_pb = float(cfg.get("ema_pullback_pct", 0.20))
    d200 = abs(last_close - ema200.iloc[-1]) / ema200.iloc[-1] * 100.0
    d100 = abs(last_close - ema100.iloc[-1]) / ema100.iloc[-1] * 100.0
    if d200 <= tol_pb:
        pb_frac = 1.0
        pb_txt = "แตะ EMA200"
    elif d100 <= tol_pb:
        pb_frac = 0.7
        pb_txt = "แตะ EMA100"
    else:
        pb_frac = 0.0
        pb_txt = "ยังไม่ถึงโซน EMA"
    add("pullback", pb_frac, f"ห่าง EMA200 {d200:.2f}% / EMA100 {d100:.2f}% → {pb_txt}")

    # 10) Rejection
    rfrac, rnote = _rejection_frac(df, direction, int(cfg.get("rejection_lookback", 2)))
    add("rejection", rfrac, rnote)

    return round(score, 2), details, grip_hits


# ── ฟังก์ชันหลัก ──────────────────────────────────────────────────────────────
def score_setup(
    df: pd.DataFrame,
    timeframe: str = "M5",
    target_hold_minutes: int = 30,
) -> SetupResult:
    cfg = load_config() or {}
    weights: dict = cfg.get("weights", {})
    max_score = int(sum(float(w) for w in weights.values()) or cfg.get("max_score", 15))

    if len(df) < 60:
        return SetupResult(
            timeframe=timeframe, target_hold_minutes=target_hold_minutes,
            max_score=max_score,
            details={"Data": {"ok": False, "frac": 0.0,
                              "note": f"แท่งไม่พอ (ต้องการ >= 60, ได้ {len(df)})", "weight": 0}},
        )

    close, high, low, open_ = df["close"], df["high"], df["low"], df["open"]
    ema50 = _calc_ema(close, 50)
    ema100 = _calc_ema(close, 100) if len(df) >= 100 else _calc_ema(close, len(df))
    ema200 = _calc_ema(close, 200) if len(df) >= 200 else _calc_ema(close, len(df))
    sma5 = _calc_sma(close, 5)
    rsi = _calc_rsi(close, 14)
    bb_mid, bb_up, bb_lo, bb_width = _calc_bollinger_bands(
        close, cfg.get("bb", {}).get("period", 20), cfg.get("bb", {}).get("std", 2.0))
    adx = _calc_adx(high, low, close, 14)
    atr = _calc_atr(high, low, close, 14)

    sr_cfg = cfg.get("sr", {})
    lookback_sr = int(sr_cfg.get("lookback", 200))
    piv_h, piv_l = _find_pivots(high.tail(lookback_sr), low.tail(lookback_sr), left=2, right=2)
    supports, resistances = _find_levels(df, cfg, lookback_sr)
    structure = _zigzag_structure(piv_h, piv_l)

    last_atr = atr.iloc[-1]
    if last_atr == 0 or np.isnan(last_atr):
        last_atr = float(close.tail(20).std() or 1.0)

    ctx = {
        "close": close, "ema50": ema50, "ema100": ema100, "ema200": ema200,
        "sma5": sma5, "rsi": rsi, "bb_mid": bb_mid, "bb_up": bb_up, "bb_lo": bb_lo,
        "bb_width": bb_width, "adx": adx.iloc[-1] if not np.isnan(adx.iloc[-1]) else 0.0,
        "atr": last_atr, "structure": structure,
        "piv_highs": piv_h, "piv_lows": piv_l, "supports": supports, "resistances": resistances,
    }

    # คำนวณคะแนนทั้ง 2 ทิศ → เลือกทิศที่แข็งกว่า
    call_score, call_details, call_grip = _score_direction(df, "CALL", ctx, cfg)
    put_score, put_details, put_grip = _score_direction(df, "PUT", ctx, cfg)

    if call_score >= put_score:
        direction, score, details, grip_hits = "CALL", call_score, call_details, call_grip
        other = "PUT"
    else:
        direction, score, details, grip_hits = "PUT", put_score, put_details, put_grip
        other = "CALL"

    score = round(score, 1)
    bias = ("BULLISH_REVERSION" if direction == "CALL" else
            "BEARISH_REVERSION" if direction == "PUT" else "")

    # ── Tier ──
    rsi_now = rsi.iloc[-1]
    fade_cfg = cfg.get("fade", {})
    dist_atr_now = abs(close.iloc[-1] - sma5.iloc[-1]) / last_atr
    rsi_ext = float(fade_cfg.get("rsi_extreme", 25))
    fade_rsi = (rsi_now <= rsi_ext) if direction == "CALL" else (rsi_now >= 100 - rsi_ext)
    fade_dist = dist_atr_now >= float(fade_cfg.get("sma5_atr", 1.5))
    fade_min_score = float(fade_cfg.get("min_score", 4))
    fade_ok = bool(fade_cfg.get("enabled", True)) and fade_rsi and fade_dist and score >= fade_min_score

    pb_ok = details.get("pullback", {}).get("frac", 0.0) >= 0.5
    rej_ok = details.get("rejection", {}).get("frac", 0.0) >= 0.5
    fire_score = float(cfg.get("fire_score", 10))
    watch_score = float(cfg.get("watch_score", 7))

    if score >= fire_score and pb_ok and rej_ok:
        tier = "FIRE"
    elif fade_ok:
        tier = "FADE"
    elif score >= watch_score and pb_ok:
        tier = "WATCH"
    else:
        tier = "NONE"

    entry_trigger = tier in ("FIRE", "FADE")
    note_parts = [f"Setup {score:.1f}/{max_score} → {tier}"]
    if tier == "FIRE":
        note_parts.append(f"ครบเงื่อนไข (≥{fire_score:.0f}) + ราคากลับมาโซน EMA + Rejection → พิจารณาเข้า {direction}")
    elif tier == "FADE":
        note_parts.append(f"Fade extreme: RSI {rsi_now:.0f} + ห่าง SMA5 {dist_atr_now:.2f}x ATR → เข้าเร็ว {direction} (ไม่ต้องรอราคากลับ EMA)")
    elif tier == "WATCH":
        note_parts.append(f"ราคากลับมาที่โซน EMA แล้ว ({score:.1f}≥{watch_score:.0f}) — รอ Rejection ยืนยันก่อนเข้า {direction}")
    else:
        note_parts.append(f"สกอร์ต่ำกว่าเกณฑ์ / ยังไม่ถึงโซน EMA (ทิศเด่น {direction} {score:.1f}, {other} {max(call_score, put_score) if direction != 'PUT' else put_score:.1f})")

    score_breakdown = {name: round(d["weight"] * d["frac"], 2)
                       for name, d in details.items()}

    return SetupResult(
        timeframe=timeframe,
        target_hold_minutes=target_hold_minutes,
        score=score,
        max_score=max_score,
        tier=tier,
        direction=direction if score >= 3 else "",
        bias=bias if score >= 3 else "",
        entry_trigger=entry_trigger,
        entry_trigger_note=" | ".join(note_parts),
        details=details,
        grip_hits=grip_hits,
        score_breakdown=score_breakdown,
        model_prob=None,
    )
