"""
setup_scorer.py — 🔵 EMA200-is-the-Heart Rule-Based Setup Engine V5 (ตามหลักการเจ้าของระบบ)
====================================================================================
ปรับตามหลักการจริงของเจ้าของระบบ:

  🎯 ใจหลักของระบบ: ราคาปัจจุบันต้อง "แตะหรือใกล้ EMA200" เท่านั้น — ห่างเมื่อไหร่ = ไม่ส่งเด็ดขาด
     ยกเว้น 2 ทาง:
       A) ราคาทะลุ EMA100 มาแล้ว (ย่อมาอยู่ระหว่าง EMA100–EMA200 ตามทิศเทรน) แต่ยังไม่แตะ EMA200
          → ส่งได้ถ้า setup รวม >= fire_score (13)
       B) ราคาแตะ/อยู่ในโซน EMA200 แล้ว (ใจหลัก) → ส่งได้แม้สกอร์ไม่ถึงเกณฑ์
          แต่ต้องตามเทรนหลัก (สวนเทรนย่อยได้) + มีแนวรับ/ต้านใกล้จุดแตะ

   ลำดับตรวจ (ตรง Setup101 ข้อ 2.1-2.10):
     1) เทรนด์ใหญ่: EMA50/100/200 เรียงตามทิศ (ห้ามสวนเทรนหลัก)
     2) ADX > 20 → เทรนด์แข็งแรง
     3) RSI อยู่ในโซน (ย่อลึกในเทรนด์ขึ้น = overbought อ่อนตัว / oversold)
     4) RSI Divergence/Convergence เพิ่มความมั่นใจ
     5) ราคาเคยทะลุ EMA100 ขึ้นไปแล้ว (ยืนยันว่าเป็นเทรนด์จริง)
     6) BB ขยายตัว (มีวอลุ่มสนับสนุน) — บีบตัว = ไม่เหมาะ
     7) Fractal (depth 15, ยอดแท่งที่ 8) ทำยอดตามทิศ — ไม่ใช่ hard gate (สวนเทรนย่อยได้)
     8) ราคาย่อลงมาอยู่โซน EMA200 (ใจหลัก)
     9) จุดย่อตรงแนวรับ/ต้านสำคัญ (หลัก/ย่อย) + มีเส้น Grip ซ้อน = ยิ่งมั่นใจ
    10) Rejection ที่ EMA200: แตะ-ดีด-แตะซ้ำ (double-touch ตามนิยามใน Setup101) → เพิ่มสกอร์

  Tier:
    FIRE  = (B) แตะ EMA200 + ตามเทรนหลัก + มีแนวใกล้จุดแตะ  |  (A) ทะลุ EMA100 + สกอร์>=13
    WATCH = ทะลุ EMA100 กำลังย่อหา EMA200 + สกอร์>=watch_score
    NONE  = ห่าง EMA200 เกินโซน (ใจหลักไม่ผ่าน) หรือสวนเทรนหลัก หรือสกอร์ไม่ถึงเกณฑ์

  ตั้งค่าได้ใน setup_config.json (โหลด auto ทุก poll)
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
    tier: str = "NONE"                       # FIRE / WATCH / NONE
    direction: str = ""                      # CALL / PUT (ตามเทรนใหญ่)
    bias: str = ""                           # BULLISH_TREND / BEARISH_TREND
    entry_trigger: bool = False              # True เฉพาะ FIRE
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


# ── Fractal Swing Detection (Bill Williams / TradingView ta.pivothigh-low, 15 แท่ง) ──
def _find_fractals(high: pd.Series, low: pd.Series, left: int = 7, right: int = 7):
    """Fractal ตรงมาตรฐาน TradingView ta.pivothigh/pivotlow:
    แท่งกลาง (i) ต้องเป็นยอดสูงสุดในหน้าต่าง [i-left, i+right] โดยแท่งซ้าย left และขวา right
    ทั้งหมดต้องต่ำกว่า (ถ้าเป็นยอดสูง) หรือสูงกว่า (ถ้าเป็นยอดต่ำ) อย่างเคร่งครัด
    → กับ left=7, right=7 ได้ยอดแท่งที่ 8 จาก 15 แท่ง (ตามที่ตั้งไว้)
    คืน piv_highs / piv_lows = [(index, price), ...] เรียงตามเวลา"""
    n = len(high)
    H = [float(x) for x in high]
    L = [float(x) for x in low]
    piv_highs: list[tuple[int, float]] = []
    piv_lows: list[tuple[int, float]] = []
    for i in range(left, n - right):
        h, l = H[i], L[i]
        is_h = h > max(H[i - left:i]) and h > max(H[i + 1:i + right + 1])
        is_l = l < min(L[i - left:i]) and l < min(L[i + 1:i + right + 1])
        if is_h:
            piv_highs.append((i, h))
        elif is_l:
            piv_lows.append((i, l))
    return piv_highs, piv_lows


def _fractal_structure(piv_highs, piv_lows) -> str:
    """โครงสร้างจาก fractal ล่าสุด: HH+HL = UPTREND, LH+LL = DOWNTREND, อื่น = SIDEWAYS"""
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
    sl = min(lookback, len(df))
    seg = df.iloc[-sl:]
    # S/R ใช้ fractal ละเอียด (left/right=2) เพื่อเก็บแนวรับ/ต้านจำนวนมาก (ตั้งค่าได้ sr.fractal_left/right)
    sr_cfg = cfg.get("sr", {})
    fleft = int(sr_cfg.get("fractal_left", 2))
    fright = int(sr_cfg.get("fractal_right", 2))
    n = len(seg)
    piv_h = []
    piv_l = []
    for i in range(fleft, n - fright):
        wh = seg["high"].iloc[i - fleft: i + fright + 1]
        if seg["high"].iloc[i] == wh.max() and wh.max() > wh.min():
            piv_h.append((i, float(seg["high"].iloc[i])))
        wl = seg["low"].iloc[i - fleft: i + fright + 1]
        if seg["low"].iloc[i] == wl.min() and wl.max() > wl.min():
            piv_l.append((i, float(seg["low"].iloc[i])))
    tol = sr_cfg.get("tolerance_pct", 0.20)
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


# ── Rejection Candle (ดูย้อนหลัง lookback แท่ง) ───────────────────────────────
def _rejection_frac(df: pd.DataFrame, direction: str, lookback: int = 3) -> tuple[float, str]:
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


# ── Rejection ที่ EMA200 (ตามนิยาม Setup101: แตะ→ดีด→แตะซ้ำ เท่านั้น) ────────
def _ema200_rejection_frac(df: pd.DataFrame, ema200: pd.Series, direction: str, cfg: dict) -> tuple[float, str]:
    """Reject ตาม Setup101 ข้อ 10 เฉพาะนิยามเดียว:
    ราคาแตะ EMA200 → ถูกดีดกลับ → กลับมาแตะซ้ำ (Double-touch) = ผ่านเท่านั้น
    ไม่มี double-touch = ไม่ผ่าน (ตัดกรณี 'แค่เคยแตะแล้วดีดออก' ออก)"""
    tol = float(cfg.get("ema200_tol_pct", 0.15))
    lookback = int(cfg.get("rejection_lookback", 10))
    n = len(df)
    e200 = float(ema200.iloc[-1])

    # นับครั้งที่แท่งแตะโซน EMA200 (low ของแท่ง ใกล้/ต่ำกว่า EMA200 ในเทรนด์ขึ้น)
    touches = []
    for k in range(lookback):
        idx = n - 1 - k
        if idx < 0:
            break
        row = df.iloc[idx]
        if direction == "CALL":
            near = float(row["low"]) <= e200 * (1 + tol / 100.0)
        else:
            near = float(row["high"]) >= e200 * (1 - tol / 100.0)
        if near:
            touches.append(k)
    if not touches:
        return 0.0, f"ราคายังไม่แตะโซน EMA200 ({tol:.2f}%) ใน {lookback} แท่ง"

    # นิยามเดียวที่ผ่าน: แท่งล่าสุดกำลังแตะ + เคยแตะมาก่อน (แตะ→ดีด→แตะซ้ำ)
    if len(touches) >= 2 and touches[0] == 0 and touches[1] > 0:
        return 1.0, f"Double-touch EMA200: แตะ-ดีด-แตะซ้ำ (แท่งก่อน {touches[1] + 1}) = Reject ตามนิยาม"
    if touches[0] == 0:
        return 0.0, "กำลังแตะ EMA200 แต่ยังไม่ครบรูปแบบ แตะ→ดีด→แตะซ้ำ (รอ double-touch)"
    return 0.0, f"เคยแตะ EMA200 ใน {touches[0] + 1} แท่งก่อน แต่ตอนนี้ดีดออกไปแล้ว — ไม่ใช่ double-touch ตามนิยาม"


# ── คะแนนตามเทรนเดียว (Trend-Aligned) ───────────────────────────────────────
def _score_trend_setup(df: pd.DataFrame, direction: str, ctx: dict, cfg: dict) -> tuple[float, dict, list[str]]:
    """ประเมิน checklist ตาม Setup101 โดยผูกกับทิศเทรนใหญ่ (direction) เท่านั้น
    — ไม่มีการให้คะแนนทิศสวนเทรน"""
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
    ema50, ema100, ema200 = ctx["ema50"], ctx["ema100"], ctx["ema200"]
    e50, e100, e200 = ema50.iloc[-1], ema100.iloc[-1], ema200.iloc[-1]
    rsi = float(ctx["rsi"].iloc[-1])
    piv_h, piv_l = ctx["piv_highs"], ctx["piv_lows"]

    # 1) เทรนด์ใหญ่ — EMA เรียงตามทิศ
    if direction == "CALL":
        align = e50 > e100 > e200
        ema_note = f"EMA50 {e50:.2f} > EMA100 {e100:.2f} > EMA200 {e200:.2f}" if align else (
            f"EMA50 {e50:.2f} / EMA100 {e100:.2f} / EMA200 {e200:.2f} — ยังไม่เรียงตามเทรนขึ้น")
    else:
        align = e50 < e100 < e200
        ema_note = f"EMA50 {e50:.2f} < EMA100 {e100:.2f} < EMA200 {e200:.2f}" if align else (
            f"EMA50 {e50:.2f} / EMA100 {e100:.2f} / EMA200 {e200:.2f} — ยังไม่เรียงตามเทรนลง")
    add("trend_ema", 1.0 if align else 0.0, ema_note)

    # 2) ADX — เทรนแข็งแรง (Setup101 ข้อ 2)
    adx = ctx["adx"]
    adx_min = float(cfg.get("adx_min", 20))
    adx_frac = 1.0 if adx >= adx_min else (0.5 if adx >= adx_min - 5 else 0.0)
    add("adx", adx_frac, f"ADX={adx:.1f} (>= {adx_min:.0f})")

    # 3) RSI — อยู่ในโซนที่เหมาะกับ pullback ตามเทรน (Setup101 ข้อ 3)
    rsi_cfg = cfg.get("rsi", {})
    if direction == "CALL":
        # เทรนด์ขึ้น: อยากได้ RSI ย่อลงจาก overbought (มี room ดีดกลับ)
        rzone_lo = float(rsi_cfg.get("overbought", 70))
        if rsi < 45:
            rfrac, rnote = 1.0, f"RSI={rsi:.1f} ย่อลึกในเทรนด์ขึ้น (โอเคสำหรับจุดกลับตัว)"
        elif rsi < rzone_lo:
            rfrac, rnote = 0.5, f"RSI={rsi:.1f} อ่อนตัวจาก overbought (ยังมี room)"
        else:
            rfrac, rnote = 0.0, f"RSI={rsi:.1f} ยัง overbought (>= {rzone_lo:.0f}) — เสี่ยงที่ราคาจะย่อต่อไป"
    else:
        rzone_hi = float(rsi_cfg.get("oversold", 30))
        if rsi > 55:
            rfrac, rnote = 1.0, f"RSI={rsi:.1f} ย่อลึกในเทรนด์ลง (โอเคสำหรับจุดกลับตัว)"
        elif rsi > rzone_hi:
            rfrac, rnote = 0.5, f"RSI={rsi:.1f} อ่อนตัวจาก oversold (ยังมี room)"
        else:
            rfrac, rnote = 0.0, f"RSI={rsi:.1f} ยัง oversold (<= {rzone_hi:.0f}) — เสี่ยงที่จะร่วงต่อ"
    add("rsi_zone", rfrac, rnote)

    # 4) RSI Divergence/Convergence — เพิ่มความมั่นใจ (Setup101 ข้อ 3)
    dfrac, dnote = _divergence_frac(ctx["rsi"], piv_l, piv_h, direction)
    add("rsi_div", dfrac, dnote)

    # 5) ราคาเคยทะลุ EMA100 มาแล้ว (ยืนยันเทรนด์จริง) (Setup101 ข้อ 8)
    look = min(20, len(close))
    recent_high = float(close.iloc[-look:].max())
    past_ema100 = float(ema100.iloc[-look:].max())
    if direction == "CALL":
        crossed = recent_high > past_ema100 * (1 + float(cfg.get("ema100_tol_pct", 0.08)) / 100.0)
        cross_note = f"ราคาเคยขึ้นเหนือ EMA100 (สูงสุด {recent_high:.2f} > {past_ema100:.2f})" if crossed else \
            f"ราคายังไม่เคยทะลุ EMA100 ใน {look} แท่ง ({recent_high:.2f})"
    else:
        crossed = recent_high < past_ema100 * (1 - float(cfg.get("ema100_tol_pct", 0.08)) / 100.0)
        cross_note = f"ราคาเคยร่วงใต้ EMA100 (ต่ำสุด {recent_high:.2f} < {past_ema100:.2f})" if crossed else \
            f"ราคายังไม่เคยหลุด EMA100 ใน {look} แท่ง ({recent_high:.2f})"
    add("ema100", 1.0 if crossed else 0.0, cross_note)

    # 6) BB — ขยายตัว (มีวอลุ่ม) ไม่ใช่บีบ (Setup101 ข้อ 5)
    width = ctx["bb_width"]
    cur_w = float(width.iloc[-1])
    avg_w = float(width.rolling(20).mean().iloc[-1]) if len(width) >= 20 else cur_w
    expanding = cur_w > avg_w
    squeeze = bool(np.isnan(avg_w)) or cur_w <= avg_w * 0.9
    if expanding and not squeeze:
        bb_note = f"BB ขยาย (width {cur_w:.2f}% > avg {avg_w:.2f}%) — มีวอลุ่มสนับสนุน"
        bb_frac = 1.0
    elif not squeeze:
        bb_note = f"BB ทรงตัว (width {cur_w:.2f}% vs avg {avg_w:.2f}%)"
        bb_frac = 0.5
    else:
        bb_note = f"BB บีบตัว (width {cur_w:.2f}%) — ยังไม่เหมาะตาม Setup101"
        bb_frac = 0.0
    add("bb", bb_frac, bb_note)

    # 7) Fractal (depth 15) — ทำยอดตามทิศเทรน (Setup101 ข้อ 6)
    struct = ctx["structure"]
    if direction == "CALL":
        ok = struct == "UPTREND"
        fr_note = f"Fractal: {struct} — HH/HL ตามเทรนขึ้น" if ok else f"Fractal: {struct} — ขัด/ยังไม่ยืนยันเทรนขึ้น"
    else:
        ok = struct == "DOWNTREND"
        fr_note = f"Fractal: {struct} — LH/LL ตามเทรนลง" if ok else f"Fractal: {struct} — ขัด/ยังไม่ยืนยันเทรนลง"
    add("structure", 1.0 if ok else 0.0, fr_note)

    # 8) Pullback — ราคาย่อมาอยู่โซน EMA200 (Setup101 ข้อ 8: อย่างน้อยผ่าน EMA100)
    tol200 = float(cfg.get("ema200_tol_pct", 0.12))
    dist200 = abs(last_close - e200) / e200 * 100.0
    if dist200 <= tol200:
        pb_frac = 1.0
        pb_note = f"ราคา {last_close:.2f} แตะโซน EMA200 {e200:.2f} (ห่าง {dist200:.2f}% ≤ {tol200:.2f}%)"
    elif dist200 <= tol200 * 2.5:
        pb_frac = 0.6
        pb_note = f"ราคา {last_close:.2f} ใกล้โซน EMA200 {e200:.2f} (ห่าง {dist200:.2f}%)"
    else:
        pb_frac = 0.0
        pb_note = f"ราคา {last_close:.2f} ยังห่าง EMA200 {e200:.2f} ({dist200:.2f}%) — ยังไม่ถึงจุดย่อ"
    add("pullback", pb_frac, pb_note)

    # 9) แนวรับ/ต้านสำคัญ + Grip (Setup101 ข้อ 9)
    tol_sr = float(cfg.get("sr", {}).get("tolerance_pct", 0.20))
    if direction == "CALL":
        near = _nearest_level(last_close, ctx["supports"])
        lvl_word = "แนวรับ"
    else:
        near = _nearest_level(last_close, ctx["resistances"])
        lvl_word = "แนวต้าน"
    grip_step = _grip_step(last_close, cfg)
    ng = _near_grip(last_close, grip_step, float(cfg.get("grip", {}).get("tolerance_pct", 0.05)))
    if near and near["dist_pct"] <= tol_sr:
        tests = near["tests"]
        major_tests = int(cfg.get("sr", {}).get("major_tests", 3))
        minor_tests = int(cfg.get("sr", {}).get("minor_tests", 2))
        if tests >= major_tests:
            frac, lvl_type = 1.0, "แนวหลัก"
        elif tests >= minor_tests:
            frac, lvl_type = 0.7, "แนวย่อย"
        else:
            frac, lvl_type = 0.5, "โซนเบา"
        if ng and tests >= minor_tests:
            frac = 1.0
            grip_hits.append("Grip")
        note = f"{lvl_type} {near['price']:.2f} เทสต์ {tests} ครั้ง ห่าง {near['dist_pct']:.2f}%"
        if ng:
            note += f" + Grip {round(last_close / grip_step) * grip_step:.2f}"
            grip_hits.append("Grip")
    else:
        frac = 0.0
        note = f"ไม่ใกล้{lvl_word}สำคัญ (tol {tol_sr:.2f}%)" + (f" | Grip ห่าง" if ng else "")
    add("sr", frac, note)

    # 10) Rejection ที่ EMA200 — จุดชี้ขาด (Setup101 ข้อ 10)
    rfrac, rnote = _ema200_rejection_frac(df, ema200, direction, cfg)
    add("rejection", rfrac, rnote)

    # 11) SMA5 — ราคาไกลจากเส้น = มีแรงหุบกลับหาเส้นค่าเฉลี่ย (Setup101 ข้อ 1.5)
    sma_cfg = cfg.get("sma5", {})
    sma5 = _calc_sma(close, int(sma_cfg.get("period", 5)))
    last_sma5 = float(sma5.iloc[-1])
    gap_pct = (last_close - last_sma5) / last_sma5 * 100.0
    sdist = float(sma_cfg.get("distance_pct", 0.30))
    if direction == "CALL":
        # จุดกลับตัวขึ้น: ราคาควรย่อต่ำกว่า SMA5 (gap ติดลบ) → จะหุบกลับขึ้น
        if gap_pct <= -sdist:
            sma_frac, sma_note = 1.0, f"ราคา {last_close:.2f} ย่อต่ำกว่า SMA5 {last_sma5:.2f} ({gap_pct:.2f}%) — มีแรงดีดกลับ"
        elif gap_pct < 0:
            sma_frac, sma_note = 0.5, f"ราคา {last_close:.2f} เริ่มย่อใต้ SMA5 {last_sma5:.2f} ({gap_pct:.2f}%)"
        else:
            sma_frac, sma_note = 0.0, f"ราคา {last_close:.2f} อยู่เหนือ SMA5 {last_sma5:.2f} ({gap_pct:.2f}%) — ยังไม่ใช่จุดย่อ"
    else:
        if gap_pct >= sdist:
            sma_frac, sma_note = 1.0, f"ราคา {last_close:.2f} ย่อสูงกว่า SMA5 {last_sma5:.2f} ({gap_pct:.2f}%) — มีแรงกดกลับ"
        elif gap_pct > 0:
            sma_frac, sma_note = 0.5, f"ราคา {last_close:.2f} เริ่มดีดเหนือ SMA5 {last_sma5:.2f} ({gap_pct:.2f}%)"
        else:
            sma_frac, sma_note = 0.0, f"ราคา {last_close:.2f} อยู่ใต้ SMA5 {last_sma5:.2f} ({gap_pct:.2f}%) — ยังไม่ใช่จุดดีด"
    add("sma5", sma_frac, sma_note)

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

    close, high, low = df["close"], df["high"], df["low"]
    ema50 = _calc_ema(close, 50)
    ema100 = _calc_ema(close, 100) if len(df) >= 100 else _calc_ema(close, len(df))
    ema200 = _calc_ema(close, 200) if len(df) >= 200 else _calc_ema(close, len(df))
    rsi = _calc_rsi(close, 14)
    bb_mid, bb_up, bb_lo, bb_width = _calc_bollinger_bands(
        close, cfg.get("bb", {}).get("period", 20), cfg.get("bb", {}).get("std", 2.0))
    adx = _calc_adx(high, low, close, 14)
    atr = _calc_atr(high, low, close, 14)

    sr_cfg = cfg.get("sr", {})
    lookback_sr = int(sr_cfg.get("lookback", 200))
    # Fractal: โครงสร้างเทรนใช้ depth 15 (left=7, right=7) → ยอดแท่งที่ 8 (ตรง TradingView ta.pivothigh)
    frac_cfg = cfg.get("fractal", {})
    frac_left = int(frac_cfg.get("left", 7))
    frac_right = int(frac_cfg.get("right", 7))
    piv_h, piv_l = _find_fractals(
        high.tail(lookback_sr), low.tail(lookback_sr),
        left=frac_left, right=frac_right,
    )
    supports, resistances = _find_levels(df, cfg, lookback_sr)
    structure = _fractal_structure(piv_h, piv_l)

    last_atr = atr.iloc[-1]
    if last_atr == 0 or np.isnan(last_atr):
        last_atr = float(close.tail(20).std() or 1.0)

    ctx = {
        "close": close, "ema50": ema50, "ema100": ema100, "ema200": ema200,
        "rsi": rsi, "bb_mid": bb_mid, "bb_up": bb_up, "bb_lo": bb_lo,
        "bb_width": bb_width, "adx": adx.iloc[-1] if not np.isnan(adx.iloc[-1]) else 0.0,
        "atr": last_atr, "structure": structure,
        "piv_highs": piv_h, "piv_lows": piv_l, "supports": supports, "resistances": resistances,
    }

    # ── กำหนดเทรนด์ใหญ่จาก EMA ก่อน → direction จะผูกกับเทรนเท่านั้น ──
    last_close = float(close.iloc[-1])
    e50, e100, e200 = ema50.iloc[-1], ema100.iloc[-1], ema200.iloc[-1]
    trend_align_up = e50 > e100 > e200
    trend_align_down = e50 < e100 < e200
    if trend_align_up:
        direction, bias = "CALL", "BULLISH_TREND"
    elif trend_align_down:
        direction, bias = "PUT", "BEARISH_TREND"
    else:
        direction, bias = "", ""

    # ไม่มีเทรนด์ชัดเจน → NONE (ไม่สวนเทรน)
    if not direction:
        return SetupResult(
            timeframe=timeframe,
            target_hold_minutes=target_hold_minutes,
            score=0.0, max_score=max_score, tier="NONE",
            direction="", bias="", entry_trigger=False,
            entry_trigger_note=(
                f"EMA ยังไม่เรียงตามเทรน (EMA50 {e50:.2f} / EMA100 {e100:.2f} / EMA200 {e200:.2f}) "
                f"— รอเทรนชัดเจนก่อน ไม่เทรดสวนเทรน"),
            details={
                "trend_ema": {"ok": False, "frac": 0.0, "weight": int(weights.get("trend_ema", 2)),
                              "note": "EMA ไม่เรียงตามทิศเทรน"},
            },
        )

    score, details, grip_hits = _score_trend_setup(df, direction, ctx, cfg)
    score = round(score, 1)

    # ── Tier ตามหลักการ "EMA200 คือใจหลักของระบบ" ──
    #  (owner: ราคาต้องแตะ/ใกล้ EMA200 เท่านั้นถึงจะเข้า; ข้อยกเว้น 2 ทางตามเงื่อนไข)
    #  กรณีที่ 1 (ข้อยกเว้น A): ราคาทะลุ EMA100 ไปแล้ว (ย่อมาอยู่ระหว่าง EMA100–EMA200)
    #    ยังไม่แตะ EMA200 → ส่งได้ถ้า setup รวม >= fire_score (13)
    #  กรณีที่ 2 (ข้อยกเว้น B): ราคาแตะ/อยู่ในโซน EMA200 (ใจหลัก) → ส่งได้แม้สกอร์ต่ำ
    #    แต่ต้องตามเทรนหลัก (สวนเทรนย่อยได้) + มีแนวรับ/ต้านใกล้จุดแตะ
    #  กรณีอื่น (ห่าง EMA200 เกินโซน + ยังไม่ทะลุ EMA100) → ไม่ส่งเด็ดขาด
    fire_score = float(cfg.get("fire_score", 13))
    watch_score = float(cfg.get("watch_score", 10))
    hg = cfg.get("hard_gates", {})

    def _ok(name: str, threshold: float = 0.5) -> bool:
        return details.get(name, {}).get("frac", 0.0) >= threshold

    trend_ok = _ok("trend_ema")                 # ตามเทรนหลัก (EMA50/100/200 เรียงทิศ)
    sr_ok = _ok("sr", 0.5)                       # อยู่ในโซนแนวรับ/ต้าน
    bb_ok = _ok("bb", 0.5)                        # ไม่บีบ (ขยาย/ทรงตัว)
    no_sideway = ctx["structure"] != "SIDEWAYS"   # ราคาไม่ sideway

    # สถานะราคาเทียบ EMA200 / EMA100 (โซนแตะ = ema200_tol_pct, โซนใกล้/ใจหลัก = ema200_near_tol_pct)
    tol_touch = float(cfg.get("ema200_tol_pct", 0.15))
    tol_near = float(cfg.get("ema200_near_tol_pct", 0.35))
    dist200_pct = abs(last_close - e200) / e200 * 100.0
    touching_ema200 = dist200_pct <= tol_touch      # แตะจริง (ย่อยของใจหลัก)
    near_ema200 = dist200_pct <= tol_near           # แตะหรือใกล้ = ใจหลักของระบบ
    # ทะลุ EMA100: ย่อมาอยู่ระหว่าง EMA100 กับโซน EMA200 ตามทิศเทรน (ข้อยกเว้น A)
    if direction == "CALL":
        crossed_ema100 = last_close < e100 * (1 + float(cfg.get("ema100_tol_pct", 0.08)) / 100.0)
    else:
        crossed_ema100 = last_close > e100 * (1 - float(cfg.get("ema100_tol_pct", 0.08)) / 100.0)
    # กลางทาง: ทะลุ EMA100 แล้วแต่ยังไม่ถึงโซนใกล้ EMA200 (ข้อยกเว้น A ยังต้องสกอร์สูง)
    between_ema = crossed_ema100 and not near_ema200

    # Hard-gate ใจหลัก: ไม่แตะ/ไม่ใกล้ EMA200 และยังไม่ทะลุ EMA100 เลย → ห้ามส่งทุกกรณี
    # (ถ้าทะลุ EMA100 แล้วถือว่ากำลังย่อหา EMA200 → เข้าข่ายข้อยกเว้น A ให้สกอร์สูงตัดสิน)
    heart_blocked = not (near_ema200 or crossed_ema100)
    if heart_blocked:
        return SetupResult(
            timeframe=timeframe,
            target_hold_minutes=target_hold_minutes,
            score=score, max_score=max_score, tier="NONE",
            direction=direction, bias=bias, entry_trigger=False,
            entry_trigger_note=(
                f"ราคา {last_close:.2f} ห่าง EMA200 {e200:.2f} ({dist200_pct:.2f}% > {tol_near:.2f}%) "
                f"และยังไม่ทะลุ EMA100 — ใจหลักของระบบไม่ผ่าน (ต้องแตะ/ใกล้ EMA200 หรืออย่างน้อยทะลุ EMA100)"),
            details=details, grip_hits=grip_hits,
            score_breakdown={name: round(d["weight"] * d["frac"], 2) for name, d in details.items()},
            model_prob=None,
        )

    # Gate รอบคอบเพิ่ม (เฉพาะกรณีสกอร์สูง / ข้อยกเว้น A) — fractal ไม่เป็น hard gate (สวนเทรนย่อยได้)
    hg_blocked: list[str] = []
    if hg.get("no_sideway", True) and not no_sideway:
        hg_blocked.append("ราคากำลัง sideway")
    if hg.get("bb", True) and not bb_ok:
        hg_blocked.append("BB กำลังบีบตัว")
    if hg.get("sr", True) and not sr_ok:
        hg_blocked.append("ไม่อยู่ในโซนแนวรับ/ต้าน")
    hard_ok = not hg_blocked

    if near_ema200 and trend_ok and sr_ok:
        # ข้อยกเว้น B (ใจหลัก): แตะ/ใกล้ EMA200 + ตามเทรนหลัก + มีแนวรับ/ต้านใกล้จุดแตะ → ส่งได้แม้สกอร์ต่ำ
        tier = "FIRE"
    elif between_ema and trend_ok and score >= fire_score and hard_ok:
        # ข้อยกเว้น A: ทะลุ EMA100 แล้ว (ยังห่างโซนแตะ) + setup รวม >= 13 + ผ่าน gate → ส่งได้
        tier = "FIRE"
    elif between_ema and trend_ok and score >= watch_score and hard_ok:
        tier = "WATCH"
    else:
        tier = "NONE"

    entry_trigger = tier == "FIRE"
    note_parts = [f"Setup {score:.1f}/{max_score} → {tier}"]
    if tier == "FIRE":
        if near_ema200:
            note_parts.append(
                f"ใจหลักผ่าน: ราคา {last_close:.2f} แตะ/ใกล้ EMA200 {e200:.2f} "
                f"({dist200_pct:.2f}%) + เทรน {direction} หลัก + แนวรับ/ต้านใกล้จุดแตะ → เข้าตามเทรน {direction}")
        else:
            note_parts.append(
                f"ทะลุ EMA100 มาแล้ว ({last_close:.2f}) ย่อเข้าหา EMA200 {e200:.2f} + setup {score:.1f} ≥ {fire_score:.0f} "
                f"+ เทรน {direction} → เข้าตามเทรน {direction}")
    elif tier == "WATCH":
        note_parts.append(
            f"ทะลุ EMA100 มาแล้วกำลังย่อหา EMA200 {e200:.2f} ({dist200_pct:.2f}%) — รอแตะโซน/สกอร์ ≥ {fire_score:.0f}")
    else:
        reason = f"สกอร์ {score:.1f} ต่ำกว่าเกณฑ์ {fire_score:.0f}"
        if not trend_ok:
            reason = f"สวนเทรนหลัก {direction} (EMA ยังไม่เรียงตามทิศ)"
        elif near_ema200 and not sr_ok:
            reason = "แตะ/ใกล้ EMA200 แล้วแต่ไม่มีแนวรับ/ต้านใกล้จุดแตะ"
        elif hg_blocked:
            reason = " / ".join(hg_blocked)
        elif not between_ema:
            reason = f"ราคายังไม่ทะลุ EMA100 ({last_close:.2f} vs EMA100 {e100:.2f})"
        else:
            reason = f"สกอร์ {score:.1f} ยังต่ำกว่า {fire_score:.0f}"
        note_parts.append(reason)

    score_breakdown = {name: round(d["weight"] * d["frac"], 2)
                       for name, d in details.items()}

    return SetupResult(
        timeframe=timeframe,
        target_hold_minutes=target_hold_minutes,
        score=score,
        max_score=max_score,
        tier=tier,
        direction=direction,
        bias=bias,
        entry_trigger=entry_trigger,
        entry_trigger_note=" | ".join(note_parts),
        details=details,
        grip_hits=grip_hits,
        score_breakdown=score_breakdown,
        model_prob=None,
    )
