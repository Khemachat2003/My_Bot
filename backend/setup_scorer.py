"""
setup_scorer.py — 🔵 Trend-Aligned EMA200 Rejection Checklist V3 (Rule-Based Setup Engine)
===================================================================================
ปรับใหม่ตาม Setup101.txt ฉบับเต็ม (หลักการที่เจ้าของระบบเทรดจริง):

  🎯 หลักการ: เทรด "ตามเทรนใหญ่" รอให้ราคาย่อกลับมาหา EMA 200 แล้วเกิด Reject → เข้า
     ตามทิศทางเทรน ไม่ใช่สวนเทรน (ไม่ fade)

  ลำดับตรวจ (ตรง Setup101 ข้อ 2.1-2.10):
    1) เทรนด์ใหญ่: EMA50/100/200 เรียงตามทิศ + Zigzag HH/HL (หรือ LH/LL)
    2) ADX > 20 → เทรนด์แข็งแรง
    3) RSI อยู่ในโซน (y่อลึกในเทรนด์ขึ้น = overbought อ่อนตัว / oversold)
    4) ราคาเคยทะลุ EMA100 ขึ้นไปแล้ว (ยืนยันว่าเป็นเทรนด์จริง ไม่ใช่แค่สวิง)
    5) BB ขยายตัว (มีวอลุ่มสนับสนุน) — บีบตัว = ไม่เหมาะ
    6) Zigzag ยังทำยอดตามทิศเทรนด์ต่อเนื่อง
    7) ราคาย่อลงมาอยู่โซน EMA200 (อย่างน้อยต้องผ่าน EMA100 มาแล้ว)
    8) จุดย่อตรงแนวรับ/ต้านสำคัญ (หลัก/ย่อย) + มีเส้น Grip ซ้อน = ยิ่งมั่นใจ
    9) Rejection ที่ EMA200: ราคาแตะ EMA200 แล้วถูกดีดกลับ (wick) หรือ
       แตะ-ดีด-แตะซ้ำ (double-touch ตามนิยามใน Setup101) → จุดชี้ขาด

  Tier:
    FIRE  = เทรนด์ชัดเจน + ราคาแตะโซน EMA200 + Reject เกิด → เข้าตามเทรน
    WATCH = เทรนด์ชัดเจน + ราคากำลังเข้าใกล้โซน EMA200 (รอ Reject ยืนยัน)
    NONE  = ไม่มีเทรนด์ชัดเจน / ยังห่าง EMA200

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


# ── Zigzag Swing Detection (depth=10, backstep=3, deviation=ATR-based) ───────
def _find_pivots(high: pd.Series, low: pd.Series, deviation_abs: float = 1.0,
                 depth: int = 10, backstep: int = 3):
    """Zigzag แบบ classic (สลับ high/low ตามลำดับ)
    deviation_abs คือระยะขั้นต่ำ (เป็นหน่วยราคา เช่น 2x ATR) ที่ราคาต้องเดิน
    ไปทิศตรงข้ามจาก pivot ก่อน จึงจะปัก pivot ใหม่"""
    n = len(high)
    pivots: list[tuple[int, float, str]] = []  # (idx, price, 'h'|'l')
    last_price = float('nan')
    last_idx = -1
    last_type = ""

    for i in range(n):
        h = float(high.iloc[i])
        l = float(low.iloc[i])
        if last_type == "":
            last_price, last_idx, last_type = l, i, "l"
            continue

        if last_type == "l":
            if l <= last_price:
                last_price, last_idx = l, i
            elif h >= last_price + deviation_abs:
                pivots.append((last_idx, last_price, "l"))
                last_price, last_idx, last_type = h, i, "h"
        else:  # last_type == "h"
            if h >= last_price:
                last_price, last_idx = h, i
            elif l <= last_price - deviation_abs:
                pivots.append((last_idx, last_price, "h"))
                last_price, last_idx, last_type = l, i, "l"

    # แยกเป็น piv_highs / piv_lows ตามลำดับเวลา
    piv_highs = [(i, p) for i, p, t in pivots if t == "h"]
    piv_lows = [(i, p) for i, p, t in pivots if t == "l"]
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
    # S/R ใช้ fractal ละเอียด (left/right=2) เพื่อเก็บแนวรับ/ต้านจำนวนมาก
    n = len(seg)
    piv_h = []
    piv_l = []
    for i in range(2, n - 2):
        wh = seg["high"].iloc[i - 2: i + 3]
        if seg["high"].iloc[i] == wh.max() and wh.max() > wh.min():
            piv_h.append((i, float(seg["high"].iloc[i])))
        wl = seg["low"].iloc[i - 2: i + 3]
        if seg["low"].iloc[i] == wl.min() and wl.max() > wl.min():
            piv_l.append((i, float(seg["low"].iloc[i])))
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

    # 7) Zigzag — ทำยอดตามทิศเทรน (Setup101 ข้อ 6)
    struct = ctx["structure"]
    if direction == "CALL":
        ok = struct == "UPTREND"
        zz_note = f"Zigzag: {struct} — HH/HL ตามเทรนขึ้น" if ok else f"Zigzag: {struct} — ขัด/ยังไม่ยืนยันเทรนขึ้น"
    else:
        ok = struct == "DOWNTREND"
        zz_note = f"Zigzag: {struct} — LH/LL ตามเทรนลง" if ok else f"Zigzag: {struct} — ขัด/ยังไม่ยืนยันเทรนลง"
    add("structure", 1.0 if ok else 0.0, zz_note)

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
    # Zigzag: ATR-based deviation (mode=atr) → ใช้ 2x ATR เป็นระยะขั้นต่ำ
    zz_cfg = cfg.get("zigzag", {})
    zz_dev = float(zz_cfg.get("atr_multiplier", 2.0)) * float(atr.iloc[-1])
    piv_h, piv_l = _find_pivots(
        high.tail(lookback_sr), low.tail(lookback_sr),
        deviation_abs=zz_dev,
        depth=int(zz_cfg.get("depth", 10)),
        backstep=int(zz_cfg.get("backstep", 3)),
    )
    supports, resistances = _find_levels(df, cfg, lookback_sr)
    structure = _zigzag_structure(piv_h, piv_l)

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

    # ── Tier (Setup101 ข้อ 3: กรณี 1/2/3) + Hard-gates ──
    fire_score = float(cfg.get("fire_score", 13))
    watch_score = float(cfg.get("watch_score", 10))
    hg = cfg.get("hard_gates", {})

    def _ok(name: str, threshold: float = 0.5) -> bool:
        return details.get(name, {}).get("frac", 0.0) >= threshold

    trend_ok = _ok("trend_ema")
    pullback_ok = _ok("pullback", 0.5)          # ราคาแตะ/ใกล้ EMA200 (หัวใจของ setup)
    reject_frac = details.get("rejection", {}).get("frac", 0.0)
    structure_ok = _ok("structure", 0.99)        # Zigzag HH/HL ตามเทรน
    bb_ok = _ok("bb", 0.5)                        # ไม่บีบ (ขยาย/ทรงตัว)
    sr_ok = _ok("sr", 0.5)                        # อยู่ในโซนแนวรับ/ต้าน
    no_sideway = ctx["structure"] != "SIDEWAYS"   # ราคาไม่ sideway

    # Hard-gates ตาม config (ค่า default: เปิดหมด) — บังคับก่อนได้ tier
    hg_blocked: list[str] = []
    if hg.get("ema200_touch", True) and not pullback_ok:
        hg_blocked.append("ราคายังไม่แตะ/ใกล้โซน EMA200")
    if hg.get("no_sideway", True) and not no_sideway:
        hg_blocked.append("ราคากำลัง sideway")
    if hg.get("structure", True) and not structure_ok:
        hg_blocked.append("Zigzag ยังไม่ทำ HH/HL ตามเทรน")
    if hg.get("bb", True) and not bb_ok:
        hg_blocked.append("BB กำลังบีบตัว")
    if hg.get("sr", True) and not sr_ok:
        hg_blocked.append("ไม่อยู่ในโซนแนวรับ/ต้าน")

    hard_ok = not hg_blocked

    if trend_ok and pullback_ok and reject_frac >= 1.0 and score >= fire_score and hard_ok:
        tier = "FIRE"
    elif trend_ok and pullback_ok and hard_ok and score >= watch_score:
        tier = "WATCH"
    else:
        tier = "NONE"

    entry_trigger = tier == "FIRE"
    note_parts = [f"Setup {score:.1f}/{max_score} → {tier}"]
    if tier == "FIRE":
        note_parts.append(f"เทรน {direction} ชัดเจน + แตะ EMA200 + Double-touch Reject + ผ่าน hard-gate → เข้าตามเทรน {direction}")
    elif tier == "WATCH":
        note_parts.append(f"เทรน {direction} ชัดเจน + แตะ EMA200 + ผ่าน hard-gate — ยังรอ Double-touch Reject (Setup101 ข้อ 10)")
    else:
        reason = f"สกอร์ {score:.1f} ต่ำกว่าเกณฑ์ {fire_score:.0f}/{watch_score:.0f}"
        if hg_blocked:
            reason = " / ".join(hg_blocked)
        elif reject_frac < 1.0:
            reason = "ยังไม่ครบ Double-touch Reject (แตะ→ดีด→แตะซ้ำ)"
        elif not pullback_ok:
            reason = "ราคายังไม่ย่อมาหา EMA200"
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
