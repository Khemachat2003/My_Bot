"""
setup_scorer.py — V9: Two-Tier Signal System (11 Checklist Conditions)
=====================================================================
Importance 1 (EMERGENCY):
  Price TOUCHES EMA200 → Fire signal IMMEDIATELY
  + Log all 11 conditions (pass/fail) for future analysis
  + "เมื่อ EMA200 แตะแล้ว เงื่อนไขใดผ่าน → ออเดอร์ชนะ"

Importance 2 (WAITING):
  Price CROSSES EMA100 but hasn't touched EMA200 yet
  → Wait until 7/11 conditions pass → Fire
  + Log all 11 conditions

11 Checklist Conditions:
  1. Fractal S/R zone alignment (lookback historical zones)
  2. Price breaks BB (direction-aware)
  3. RSI OVB/OVS (70/30)
  4. RSI Divergence at fractal S/R (divergence only, no convergence)
  5. ADX > 20 (log value for analysis)
  6. Price Action: Hammer / Doji at horizontal zone
  7. Trend from fractal swing high/low (HH/HL = uptrend)
  8. Grip (round numbers) ±0.5 gold / scaled forex
  9. BB squeeze or expansion (direct comparison)
  10. Multi-timeframe trend: EMA50>100>200 alignment (M1/M15/M30/H1/H4, 3/5)
  11. EMA Slope: Linear Regression + Normalize (Upward/Downward/Horizontal)
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
    max_score: int = 10
    tier: str = "NONE"
    direction: str = ""
    bias: str = ""
    entry_trigger: bool = False
    entry_trigger_note: str = ""
    details: dict[str, dict] = field(default_factory=dict)
    grip_hits: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)
    model_prob: float | None = None
    ema200_price: float | None = None
    dist200_pct: float | None = None
    near_ema200: bool = False
    touched_ema200: bool = False
    crossed_ema100: bool = False
    # V8: Two-tier system
    importance: int = 0          # 1 = EMA200 touch (emergency), 2 = EMA100 cross (waiting)
    conditions_passed: int = 0   # How many of 10 conditions passed
    conditions_total: int = 10
    conditions_log: dict = field(default_factory=dict)  # Full log of all 10 conditions
    touch_case: str = ""         # TICK_TOUCH / WICK_TOUCH / CLOSE_TOUCH / ""


# ── Indicators ────────────────────────────────────────────────────────────────
def _calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


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


# ── Fractal Detection (Williams Fractal 15: 7 left, 1 center, 7 right) ─────
def _find_fractals(high: pd.Series, low: pd.Series, left: int = 7, right: int = 7):
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


# ══════════════════════════════════════════════════════════════════════════════
# 10 CONDITIONS
# ══════════════════════════════════════════════════════════════════════════════

def _cond1_fractal_sr(df: pd.DataFrame, piv_highs, piv_lows, direction: str,
                       zone_tol_pct: float = 0.3) -> dict:
    """Fractal S/R zone — มองย้อนหลังหา fractal ที่อยู่ในโซนราคาเดียวกัน
    ใช้ zone_tol_pct (default 0.3%) เป็นรัศมีจากตำแหน่ง fractal"""
    last_close = float(df["close"].iloc[-1])

    # ตรวจ fractal ทุกตัว (most recent ก่อน) — ถ้าเจอตัวไหนตรงโซน → pass
    for idx, price in reversed(piv_highs):
        if idx < len(df):
            row = df.iloc[idx]
            body_top = max(float(row["open"]), float(row["close"]))
            body_bot = min(float(row["open"]), float(row["close"]))
            zone_hi = price * (1 + zone_tol_pct / 100)
            zone_lo = body_bot * (1 - zone_tol_pct / 100)
            if zone_lo <= last_close <= zone_hi:
                return {"pass": True,
                        "note": f"ราคาอยู่ในโซนแนวต้าน fractal "
                                f"({body_bot:.2f}–{price:.2f}) ±{zone_tol_pct}%"}

    for idx, price in reversed(piv_lows):
        if idx < len(df):
            row = df.iloc[idx]
            body_top = max(float(row["open"]), float(row["close"]))
            body_bot = min(float(row["open"]), float(row["close"]))
            zone_hi = body_top * (1 + zone_tol_pct / 100)
            zone_lo = price * (1 - zone_tol_pct / 100)
            if zone_lo <= last_close <= zone_hi:
                return {"pass": True,
                        "note": f"ราคาอยู่ในโซนแนวรับ fractal "
                                f"({price:.2f}–{body_top:.2f}) ±{zone_tol_pct}%"}

    return {"pass": False, "note": "ราคาไม่ได้อยู่ในโซน S/R จาก fractal"}


def _cond2_bb_break(df: pd.DataFrame, bb_up, bb_lo, direction: str) -> dict:
    """Price breaks BB"""
    last_close = float(df["close"].iloc[-1])
    last_up = float(bb_up.iloc[-1]) if not np.isnan(bb_up.iloc[-1]) else 0
    last_lo = float(bb_lo.iloc[-1]) if not np.isnan(bb_lo.iloc[-1]) else 0
    
    if direction == "CALL" and last_close <= last_lo:
        return {"pass": True, "note": f"ราคา {last_close:.2f} ทะลุ BB ล่าง {last_lo:.2f}"}
    elif direction == "PUT" and last_close >= last_up:
        return {"pass": True, "note": f"ราคา {last_close:.2f} ทะลุ BB บน {last_up:.2f}"}
    
    return {"pass": False, "note": f"ราคา {last_close:.2f} ไม่ได้ทะลุ BB ({last_lo:.2f}-{last_up:.2f})"}


def _cond3_rsi_ob_os(rsi_val: float, direction: str) -> dict:
    """RSI OVB/OVS — 70/30"""
    if direction == "CALL" and rsi_val < 30:
        return {"pass": True, "note": f"RSI={rsi_val:.1f} oversold (<30)"}
    elif direction == "PUT" and rsi_val > 70:
        return {"pass": True, "note": f"RSI={rsi_val:.1f} overbought (>70)"}
    return {"pass": False, "note": f"RSI={rsi_val:.1f} ไม่ใช่ OVB/OVS"}


def _cond4_rsi_divergence(rsi: pd.Series, piv_highs, piv_lows, direction: str,
                          last_close: float) -> dict:
    """RSI Divergence — เทียบราคา vs RSI ณ จุด fractal vs จุดปัจจุบัน
    Divergence เท่านั้น (ไม่ใช้ convergence)

    CALL: หา fractal LOW ล่าสุด → ราคาจากจุดนั้นขึ้นมา แต่ RSI ลง = Bullish Div
    PUT:  หา fractal HIGH ล่าสุด → ราคาจากจุดนั้นลงมา แต่ RSI ขึ้น = Bearish Div
    """
    last_rsi = float(rsi.iloc[-1]) if len(rsi) > 0 else 50.0

    # ── Approach 1: Single-fractal divergence (สเปคผู้ใช้) ──
    if direction == "CALL" and len(piv_lows) >= 1:
        i_frac, p_frac = piv_lows[-1]
        if i_frac < len(rsi):
            r_frac = float(rsi.iloc[i_frac])
            # ราคาจาก fractal low → ปัจจุบัน = ขึ้น (p_now > p_frac)
            # RSI ลดลง (r_now < r_frac) = Bullish Divergence
            if last_close > p_frac and last_rsi < r_frac:
                return {"pass": True,
                        "note": (f"Bullish Divergence: ราคา {p_frac:.2f}→{last_close:.2f} (↑) "
                                 f"RSI {r_frac:.1f}→{last_rsi:.1f} (↓)")}

    if direction == "PUT" and len(piv_highs) >= 1:
        i_frac, p_frac = piv_highs[-1]
        if i_frac < len(rsi):
            r_frac = float(rsi.iloc[i_frac])
            # ราคาจาก fractal high → ปัจจุบัน = ลง (p_now < p_frac)
            # RSI เพิ่มขึ้น (r_now > r_frac) = Bearish Divergence
            if last_close < p_frac and last_rsi > r_frac:
                return {"pass": True,
                        "note": (f"Bearish Divergence: ราคา {p_frac:.2f}→{last_close:.2f} (↓) "
                                 f"RSI {r_frac:.1f}→{last_rsi:.1f} (↑)")}

    # ── Approach 2: 2-fractal divergence (standard) ──
    if direction == "CALL" and len(piv_lows) >= 2:
        (i1, p1), (i2, p2) = piv_lows[-2], piv_lows[-1]
        r1, r2 = float(rsi.iloc[i1]), float(rsi.iloc[i2])
        if p2 < p1 and r2 > r1:
            return {"pass": True,
                    "note": (f"Bullish Div (2-fractal): ราคา {p1:.2f}→{p2:.2f} (LL) "
                             f"RSI {r1:.1f}→{r2:.1f} (HL)")}

    if direction == "PUT" and len(piv_highs) >= 2:
        (i1, p1), (i2, p2) = piv_highs[-2], piv_highs[-1]
        r1, r2 = float(rsi.iloc[i1]), float(rsi.iloc[i2])
        if p2 > p1 and r2 < r1:
            return {"pass": True,
                    "note": (f"Bearish Div (2-fractal): ราคา {p1:.2f}→{p2:.2f} (HH) "
                             f"RSI {r1:.1f}→{r2:.1f} (LH)")}

    return {"pass": False, "note": "ไม่พบ Divergence"}


def _cond5_adx(adx_val: float) -> dict:
    """ADX > 20 + log ค่า ADX เต็มใน note สำหรับวิเคราะห์"""
    if adx_val >= 20:
        return {"pass": True, "note": f"ADX={adx_val:.1f} (>=20) เทรนแข็งแรง"}
    return {"pass": False, "note": f"ADX={adx_val:.1f} (<20) เทรนอ่อน"}


def _cond6_pa_confirmation(df: pd.DataFrame, direction: str,
                            piv_highs=None, piv_lows=None,
                            zone_tol_pct: float = 0.3) -> dict:
    """PA ณ โซนราคาเดียวกัน — Hammer + Doji เท่านั้น
    ดูแนวนอนย้อนหลังใน buffer หาแท่งที่อยู่ในโซนราคาเดียวกัน
    กรณีพิเศษ: ถ้า PA ตรงกับ fractal zone → บอกระบุว่า 'PA point'"""
    last_close = float(df["close"].iloc[-1])
    zone_hi = last_close * (1 + zone_tol_pct / 100)
    zone_lo = last_close * (1 - zone_tol_pct / 100)

    # สร้าง set ของ fractal zones เพื่อตรวจ special case
    frac_zones = set()
    if piv_highs:
        for idx, price in piv_highs:
            if idx < len(df):
                row = df.iloc[idx]
                frac_zones.add((round(price, 2), "H"))
    if piv_lows:
        for idx, price in piv_lows:
            if idx < len(df):
                row = df.iloc[idx]
                frac_zones.add((round(price, 2), "L"))

    n = len(df)
    search_limit = min(n, 200)
    for k in range(search_limit):
        idx = n - 1 - k
        if idx < 0:
            break
        row = df.iloc[idx]
        o = float(row["open"])
        h = float(row["high"])
        lo = float(row["low"])
        c = float(row["close"])

        mid = (h + lo) / 2
        if not (zone_lo <= mid <= zone_hi):
            continue

        body = abs(c - o)
        full_range = h - lo
        if full_range == 0:
            continue
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - lo

        # ── Doji: body ≈ upper wick ≈ lower wick (ทั้ง 3 ใกล้เคียงกัน) ──
        if body < full_range * 0.1:
            avg_wick = (upper_wick + lower_wick) / 2
            if avg_wick > 0 and abs(upper_wick - lower_wick) < avg_wick * 0.5:
                pa_type = "Doji"
                # ตรวจ special case: ตรงกับ fractal zone?
                is_frac_point = any(
                    abs(round(mid, 2) - fz[0]) / max(fz[0], 0.001) < 0.001
                    for fz in frac_zones
                )
                note = f"Doji ที่โซนราคา {last_close:.2f}"
                if is_frac_point:
                    note = f"PA point — Doji ตรงโซน fractal ({last_close:.2f})"
                return {"pass": True, "note": note}

        # ── Hammer (CALL): body เล็ก + ไส้ล่างยาว ≥2x body + ไส้บนสั้น ──
        if direction == "CALL" and body > 0:
            if lower_wick >= body * 2 and upper_wick < body * 0.5:
                pa_type = "Hammer"
                is_frac_point = any(
                    abs(round(mid, 2) - fz[0]) / max(fz[0], 0.001) < 0.001
                    for fz in frac_zones
                )
                note = f"Hammer ที่โซนราคา {last_close:.2f}"
                if is_frac_point:
                    note = f"PA point — Hammer ตรงโซน fractal ({last_close:.2f})"
                return {"pass": True, "note": note}

        # ── Shooting Star (PUT): body เล็ก + ไส้บนยาว ≥2x body + ไส้ล่างสั้น ──
        if direction == "PUT" and body > 0:
            if upper_wick >= body * 2 and lower_wick < body * 0.5:
                pa_type = "Shooting Star"
                is_frac_point = any(
                    abs(round(mid, 2) - fz[0]) / max(fz[0], 0.001) < 0.001
                    for fz in frac_zones
                )
                note = f"Shooting Star ที่โซนราคา {last_close:.2f}"
                if is_frac_point:
                    note = f"PA point — Shooting Star ตรงโซน fractal ({last_close:.2f})"
                return {"pass": True, "note": note}

    return {"pass": False, "note": "ไม่พบ Hammer/Doji ในโซนราคา"}


def _cond7_fractal_trend(structure: str, direction: str) -> dict:
    """Trend from fractal swing high/low"""
    if direction == "CALL" and structure == "UPTREND":
        return {"pass": True, "note": f"Fractal: {structure} — HH/HL ตามเทรนขึ้น"}
    elif direction == "PUT" and structure == "DOWNTREND":
        return {"pass": True, "note": f"Fractal: {structure} — LH/LL ตามเทรนลง"}
    return {"pass": False, "note": f"Fractal: {structure} — ไม่ตรงทิศ {direction}"}


def _cond8_grip(ema200_price: float, cfg: dict, symbol: str = "") -> dict:
    """Grip (round numbers) — absolute tolerance ±0.5 สำหรับทอง, scale สำหรับคู่อื่น"""
    # กำหนด step + tolerance ตามประเภทราคา
    sym = symbol.upper()
    if "XAU" in sym:
        step, tol = 1.0, 0.5      # ทอง: round ทุก 1.0, ±0.5
    elif "JPY" in sym:
        step, tol = 0.1, 0.05     # JPY: round ทุก 0.1, ±0.05
    elif sym in ("GBPUSD", "GBPJPY", "GBPAUD", "GBPNZD", "GBPCAD", "GBPCHF"):
        step, tol = 0.01, 0.005
    elif sym in ("EURJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY"):
        step, tol = 0.1, 0.05
    elif sym in ("EURAUD", "EURNZD", "EURCAD", "EURCHF", "EURGBP"):
        step, tol = 0.01, 0.005
    elif sym in ("AUDCAD", "AUDCHF", "AUDNZD", "NZDCAD", "NZDCHF", "CADCHF"):
        step, tol = 0.01, 0.005
    else:
        # default: ใช้ price magnitude
        if ema200_price > 100:
            step, tol = 1.0, 0.5
        elif ema200_price > 10:
            step, tol = 0.1, 0.05
        else:
            step, tol = 0.01, 0.005

    line = round(ema200_price / step) * step
    dist = abs(ema200_price - line)

    if dist <= tol:
        return {"pass": True,
                "note": f"EMA200 ({ema200_price:.2f}) ใกล้เลขกลม {line:.2f} "
                        f"(±{dist:.3f} ≤ {tol})"}
    return {"pass": False,
            "note": f"EMA200 ({ema200_price:.2f}) ห่างจากเลขกลม {line:.2f} "
                    f"(±{dist:.3f} > {tol})"}


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


def _cond9_bb_width(bb_width: pd.Series) -> dict:
    """BB squeeze or expansion — เปรียบเทียบตรงๆ ไม่มี buffer"""
    cur_w = float(bb_width.iloc[-1]) if not np.isnan(bb_width.iloc[-1]) else 0
    avg_w = float(bb_width.rolling(20).mean().iloc[-1]) if len(bb_width) >= 20 else cur_w
    
    if cur_w > avg_w:
        return {"pass": True, "note": f"BB ขยาย (width {cur_w:.2f}% > avg {avg_w:.2f}%) — มีวอลุ่ม"}
    elif cur_w < avg_w:
        return {"pass": True, "note": f"BB บีบ (width {cur_w:.2f}% < avg {avg_w:.2f}%) — เตรียม breakout"}
    return {"pass": False, "note": f"BB ทรงตัว ({cur_w:.2f}% = avg {avg_w:.2f}%)"}


def _cond10_mtf_trend(df: pd.DataFrame, direction: str) -> dict:
    """Multi-timeframe trend: M1, M15, M30, H1, H4
    ตรวจ EMA50 > EMA100 > EMA200 (หรือกลับกัน) + ราคา vs EMA200
    ต้อง ≥ 3/5 TFs ตรงทิศ"""
    close = df["close"]
    tf_configs = [
        ("M1", 1), ("M15", 15), ("M30", 30), ("H1", 60), ("H4", 240),
    ]

    aligned_count = 0
    tf_results = []

    for tf_name, tf_minutes in tf_configs:
        try:
            resampled = close.resample(
                f"{tf_minutes}min", closed="left", label="last"
            ).last().dropna()
            if len(resampled) < 200:
                tf_results.append(f"{tf_name}: ข้อมูลไม่พอ")
                continue

            e50 = float(resampled.ewm(span=50, adjust=False).mean().iloc[-1])
            e100 = float(resampled.ewm(span=100, adjust=False).mean().iloc[-1])
            e200 = float(resampled.ewm(span=200, adjust=False).mean().iloc[-1])
            p = float(resampled.iloc[-1])

            if direction == "CALL":
                aligned = (e50 > e100 > e200) and (p > e200)
            else:
                aligned = (e50 < e100 < e200) and (p < e200)

            if aligned:
                aligned_count += 1
                tf_results.append(f"{tf_name}: ✅")
            else:
                tf_results.append(f"{tf_name}: ❌")
        except Exception:
            tf_results.append(f"{tf_name}: error")

    passed = aligned_count >= 3
    return {"pass": passed,
            "note": f"MTF {aligned_count}/5 TFs ตรงทิศ ({', '.join(tf_results)})"}


def _cond11_ema_slope(ema50: pd.Series, ema100: pd.Series, ema200: pd.Series,
                      threshold: float = 0.005) -> dict:
    """EMA Slope Classification — Linear Regression + Normalize
    EMA50 lookback=5, EMA100=10, EMA200=15, threshold T=0.005%
    Returns: Upward / Downward / Horizontal"""
    def _slope_status(series: pd.Series, lookback: int, label: str):
        vals = series.dropna().values
        if len(vals) < lookback:
            return None, f"{label}: ข้อมูลไม่พอ"
        window = vals[-lookback:]
        x = np.arange(lookback, dtype=float)
        m, _ = np.polyfit(x, window, 1)
        current_val = float(window[-1])
        if current_val == 0:
            return None, f"{label}: ค่าเป็น 0"
        norm_slope = (m / current_val) * 100.0
        if norm_slope > threshold:
            return "Upward", f"{label}: ↑ {norm_slope:+.4f}%"
        elif norm_slope < -threshold:
            return "Downward", f"{label}: ↓ {norm_slope:+.4f}%"
        else:
            return "Horizontal", f"{label}: → {norm_slope:+.4f}%"

    s50, n50 = _slope_status(ema50, 5, "EMA50")
    s100, n100 = _slope_status(ema100, 10, "EMA100")
    s200, n200 = _slope_status(ema200, 15, "EMA200")

    statuses = [s for s in [s50, s100, s200] if s is not None]
    notes = [n for n in [n50, n100, n200] if n]

    # Pass = ทั้ง 3 เส้นชี้ไปทางเดียวกัน (ไม่ใช่ Horizontal ทั้งหมด)
    if len(statuses) == 3:
        all_up = all(s == "Upward" for s in statuses)
        all_down = all(s == "Downward" for s in statuses)
        passed = all_up or all_down
    else:
        passed = False

    result_status = "Mixed"
    if len(statuses) == 3:
        if all_up:
            result_status = "ALL_UP"
        elif all_down:
            result_status = "ALL_DOWN"
        else:
            result_status = "Mixed"

    return {"pass": passed,
            "note": f"EMA Slope [{result_status}]: {' | '.join(notes)}"}


# ══════════════════════════════════════════════════════════════════════════════
# EMA200 TOUCH Detection
# ══════════════════════════════════════════════════════════════════════════════
def classify_ema200_touch(c_open: float, c_high: float, c_low: float,
                          c_close: float, e200: float) -> tuple[bool, str, str, str]:
    """Classifier กลาง 3 เคสการแตะ EMA200 — ใช้ร่วมกันทั้ง real-time checker
    (setup_feed._check_tick_touch) และ rulebase checklist (_ema200_touch检测)
    เพื่อให้ทั้ง 2 ระบบส่งสัญญาณด้วยหลักการเดียวกัน

    "แตะ" = เส้น EMA200 อยู่ใน range ของแท่ง (low ≤ EMA200 ≤ high) — ไม่ใช้รัศมี

    Returns: (touched, touch_case, note, direction)
      touch_case: BREAKOUT / WICK_BOUNCE / TICK_TOUCH / ""
      direction: CALL / PUT (ฝั่งของ close เทียบเส้น)
    """
    if e200 <= 0:
        return False, "", "EMA200 ไม่ถูกต้อง", ""

    # แตะจริง = เส้นอยู่ใน range แท่งเทียน
    if not (c_low <= e200 <= c_high):
        return False, "", f"แท่งไม่ได้แตะ EMA200 ({e200:.5f})", ""

    direction = "CALL" if c_close >= e200 else "PUT"
    body = abs(c_close - c_open)
    # ทะลุจริง = เปิด-ปิดอยู่คนละฝั่งของเส้น
    crossed = (c_open - e200) * (c_close - e200) < 0

    # เคส 3: BREAKOUT — เปิด-ปิดคนละฝั่งเส้น + dist(เส้น→close) ≥ ½ body
    if crossed and body > 0 and abs(c_close - e200) >= 0.5 * body:
        return True, "BREAKOUT", (
            f"ปิดทะลุ EMA200 ({e200:.5f}) dist(เส้น→close)={abs(c_close-e200):.5f} "
            f"≥ ½body({0.5*body:.5f})"), direction

    # เคส 2: WICK_BOUNCE — wick แตะเส้น ปิดกลับ dist(wick→close) ≥ ½ body
    wick_to_close = (c_close - c_low) if c_close >= e200 else (c_high - c_close)
    if body > 0 and wick_to_close >= 0.5 * body:
        return True, "WICK_BOUNCE", (
            f"wick แตะ EMA200 ({e200:.5f}) เด้ง dist(wick→close)={wick_to_close:.5f} "
            f"≥ ½body({0.5*body:.5f})"), direction

    # เคส 1: TICK_TOUCH — แตะแล้วส่งเลย
    return True, "TICK_TOUCH", f"ราคาแตะ EMA200 ({e200:.5f}) real-time", direction


def _ema200_touch检测(df: pd.DataFrame, ema200: pd.Series,
                       lookback: int = 20) -> tuple[bool, str, str]:
    """ตรวจว่าแท่งล่าสุด (k=0) แตะ EMA200 หรือไม่ — ใช้ classify_ema200_touch กลาง
    Returns: (touched, note, touch_case)
    touch_case: BREAKOUT / WICK_BOUNCE / TICK_TOUCH / ""
    """
    n = len(df)
    idx = n - 1
    if idx < 0:
        return False, "ไม่มีข้อมูล", ""

    row = df.iloc[idx]
    e_at_bar = float(ema200.iloc[idx]) if idx < len(ema200) else float(ema200.iloc[-1])
    touched, case, note, _dir = classify_ema200_touch(
        float(row["open"]), float(row["high"]),
        float(row["low"]), float(row["close"]), e_at_bar,
    )
    return touched, note, case


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SCORING FUNCTION
# ══════════════════════════════════════════════════════════════════════════════
def score_setup(
    df: pd.DataFrame,
    timeframe: str = "M5",
    target_hold_minutes: int = 30,
    symbol: str = "",
) -> SetupResult:
    cfg = load_config() or {}
    max_score = 11
    
    if len(df) < 210:
        return SetupResult(
            timeframe=timeframe, target_hold_minutes=target_hold_minutes,
            max_score=max_score,
            details={"Data": {"ok": False, "frac": 0.0,
                              "note": f"แท่งไม่พอ (ต้องการ >= 210 สำหรับ EMA200, ได้ {len(df)})", "weight": 0}},
        )
    
    close, high, low = df["close"], df["high"], df["low"]
    ema50 = _calc_ema(close, 50)
    ema100 = _calc_ema(close, 100)
    ema200 = _calc_ema(close, 200)
    rsi = _calc_rsi(close, 14)
    bb_mid, bb_up, bb_lo, bb_width = _calc_bollinger_bands(close)
    adx = _calc_adx(high, low, close, 14)
    
    frac_left = int(cfg.get("fractal", {}).get("left", 7))
    frac_right = int(cfg.get("fractal", {}).get("right", 7))
    piv_h, piv_l = _find_fractals(high, low, left=frac_left, right=frac_right)
    structure = _fractal_structure(piv_h, piv_l)
    
    last_close = float(close.iloc[-1])
    e50, e100, e200 = float(ema50.iloc[-1]), float(ema100.iloc[-1]), float(ema200.iloc[-1])
    adx_val = float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0
    rsi_val = float(rsi.iloc[-1])
    
    # ── CHECK EMA200 TOUCH FIRST (Importance 1 ต้องทำงานแม้ EMA ไม่เรียง) ──
    dist200 = abs(last_close - e200) / e200 * 100.0
    touched, touch_note, touch_case = _ema200_touch检测(df, ema200)
    near_ema200 = dist200 <= float(cfg.get("ema200_near_tol_pct", 0.20)) or touched
    importance1 = touched

    # ── Determine trend direction from EMA order ──
    trend_align_up = e50 > e100 > e200
    trend_align_down = e50 < e100 < e200
    
    if trend_align_up:
        direction, bias = "CALL", "BULLISH_TREND"
    elif trend_align_down:
        direction, bias = "PUT", "BEARISH_TREND"
    else:
        direction, bias = "", ""
    
    # Importance 1 แตะ EMA200 → infer direction จากตำแหน่งราคา vs EMA200
    if importance1 and not direction:
        if last_close >= e200:
            direction, bias = "CALL", "EMA200_BOUNCE_UP"
        else:
            direction, bias = "PUT", "EMA200_BOUNCE_DOWN"
    
    # No clear trend and no EMA200 touch → NONE
    if not direction:
        return SetupResult(
            timeframe=timeframe,
            target_hold_minutes=target_hold_minutes,
            score=0.0, max_score=max_score, tier="NONE",
            direction="", bias="", entry_trigger=False,
            ema200_price=e200,
            dist200_pct=round(dist200, 4),
            near_ema200=False, touched_ema200=False,
            entry_trigger_note="EMA ไม่เรียงตามเทรน — รอเทรนชัดเจน",
            details={"ema_trend": {"ok": False, "frac": 0.0, "weight": 1, "note": "EMA ไม่เรียง"}},
        )
    
    # ════════════════════════════════════════════════════════════════════════
    # CHECK EMA100 CROSS
    # ════════════════════════════════════════════════════════════════════════
    _ema100_tol = float(cfg.get("ema100_tol_pct", 0.02))
    if direction == "CALL":
        crossed_ema100 = (e200 * 0.999 <= last_close <= e100 * (1 + _ema100_tol / 100))
    else:
        # ต้องอยู่ระหว่าง EMA200 (ล่าง) กับ EMA100 (บน) = pullback จริง
        crossed_ema100 = (e100 * (1 - _ema100_tol / 100) <= last_close <= e200 * 1.001)
    
    # ════════════════════════════════════════════════════════════════════════
    # EVALUATE ALL 10 CONDITIONS
    # ════════════════════════════════════════════════════════════════════════
    cond = {}
    cond["c1_fractal_sr"] = _cond1_fractal_sr(df, piv_h, piv_l, direction)
    cond["c2_bb_break"] = _cond2_bb_break(df, bb_up, bb_lo, direction)
    cond["c3_rsi_ob_os"] = _cond3_rsi_ob_os(rsi_val, direction)
    cond["c4_rsi_div"] = _cond4_rsi_divergence(rsi, piv_h, piv_l, direction, last_close)
    cond["c5_adx"] = _cond5_adx(adx_val)
    cond["c6_pa"] = _cond6_pa_confirmation(df, direction, piv_h, piv_l)
    cond["c7_fractal_trend"] = _cond7_fractal_trend(structure, direction)
    cond["c8_grip"] = _cond8_grip(e200, cfg, symbol)
    cond["c9_bb_width"] = _cond9_bb_width(bb_width)
    cond["c10_mtf"] = _cond10_mtf_trend(df, direction)
    cond["c11_ema_slope"] = _cond11_ema_slope(ema50, ema100, ema200)
    
    passed_count = sum(1 for c in cond.values() if c["pass"])
    
    # ════════════════════════════════════════════════════════════════════════
    # TIER DETERMINATION
    # ════════════════════════════════════════════════════════════════════════
    
    if importance1:
        # ═══ IMPORTANCE 1: แตะ EMA200 → FIRE ทันที (เก็บ log ทุก checklist ไว้วิเคราะห์น้ำหนัก) ═══
        importance = 1
        tier = "FIRE"
        entry_trigger = True
        passed_names = [k for k, v in cond.items() if v["pass"]]
        touch_labels = {
            "TICK_TOUCH": "⏱ ราคาแตะ EMA200 real-time",
            "WICK_BOUNCE": "📉 Wick แตะเส้นแล้วเด้ง (≥½ body)",
            "BREAKOUT": "💥 ปิดทะลุ EMA200 (≥½ body)",
            "WICK_TOUCH": "📉 Wick แตะ EMA200 (แท่งปิดห่าง)",
            "CLOSE_TOUCH": "📍 ปิดตรง EMA200",
        }
        touch_txt = touch_labels.get(touch_case, touch_note)
        note_parts = [
            f"🚨 IMPORTANCE 1 [{touch_case}]",
            f"{touch_txt} | EMA200 = {e200:.2f}",
            f"ผ่าน {passed_count}/11: {', '.join(passed_names) or 'none'}",
            f"เข้า {direction} | กรุณาสังเกตว่าเข้าจุดไหน winrate ดีสุด",
        ]

    elif crossed_ema100:
        # ═══ IMPORTANCE 2: EMA100 CROSSED → WAIT FOR 7/10 ═══
        importance = 2
        if passed_count >= 7:
            tier = "FIRE"
            entry_trigger = True
            note_parts = [
                f"⏳ IMPORTANCE 2 — ทะลุ EMA100 แล้ว + ผ่าน {passed_count}/11 เงื่อนไข",
                f"EMA100 = {e100:.2f} | EMA200 = {e200:.2f}",
                f"เข้า {direction} ตามเทรน {bias}",
            ]
        else:
            tier = "WATCH"
            entry_trigger = False
            note_parts = [
                f"⏳ IMPORTANCE 2 — ทะลุ EMA100 แล้ว แต่ผ่านแค่ {passed_count}/11 (ต้อง >=7)",
                f"รอ confirm เพิ่ม",
            ]
    else:
        # ห่าง EMA200 + ยังไม่ทะลุ EMA100 → NONE
        importance = 0
        tier = "NONE"
        entry_trigger = False
        note_parts = [
            f"❌ ราคา {last_close:.2f} ห่าง EMA200 {e200:.2f} ({dist200:.2f}%)",
            f"และยังไม่ทะลุ EMA100 — ยังไม่เข้าเงื่อนไขใด",
        ]
    
    # Build details for DB storage
    details = {}
    for name, c in cond.items():
        details[name] = {
            "ok": c["pass"],
            "frac": 1.0 if c["pass"] else 0.0,
            "weight": 1,
            "note": c["note"],
        }
    
    score_breakdown = {name: (1.0 if c["pass"] else 0.0) for name, c in cond.items()}
    
    return SetupResult(
        timeframe=timeframe,
        target_hold_minutes=target_hold_minutes,
        score=float(passed_count),
        max_score=max_score,
        tier=tier,
        direction=direction,
        bias=bias,
        entry_trigger=entry_trigger,
        entry_trigger_note=" | ".join(note_parts),
        details=details,
        grip_hits=["Grip"] if cond["c8_grip"]["pass"] else [],
        score_breakdown=score_breakdown,
        model_prob=None,
        ema200_price=e200,
        dist200_pct=round(dist200, 4),
        near_ema200=near_ema200,
        touched_ema200=touched,
        crossed_ema100=crossed_ema100,
        importance=importance,
        conditions_passed=passed_count,
        conditions_total=11,
        conditions_log=cond,
        touch_case=touch_case if importance1 else "",
    )
