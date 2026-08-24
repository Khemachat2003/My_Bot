"""
setup_scorer.py — V8: Two-Tier Signal System (Owner's Complete Trading Logic)
============================================================================
Importance 1 (EMERGENCY):
  Price TOUCHES EMA200 → Fire signal IMMEDIATELY
  + Log all 10 conditions (pass/fail) for future analysis
  + "เมื่อ EMA200 แตะแล้ว เงื่อนไขใดผ่าน → ออเดอร์ชนะ"

Importance 2 (WAITING):
  Price CROSSES EMA100 but hasn't touched EMA200 yet
  → Wait until 7/10 conditions pass → Fire
  + Log all 10 conditions

10 Checklist Conditions:
  1. Fractal 15 S/R zone alignment
  2. Price breaks BB (oversold/overbought)
  3. RSI OVB/OVS
  4. RSI Divergence/Convergence at fractal S/R points
  5. ADX > 20
  6. Price Action (PA) confirmation at S/R zone
  7. Trend from fractal swing high/low
  8. Grip (round numbers) near EMA200
  9. BB squeeze or expansion
  10. Multi-timeframe trend (M1, M30, H1, H4, D1) — need 3/5 TFs aligned
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

def _cond1_fractal_sr(df: pd.DataFrame, piv_highs, piv_lows, direction: str) -> dict:
    """Fractal 15 S/R zone alignment"""
    last_close = float(df["close"].iloc[-1])
    
    for idx, price in reversed(piv_highs):
        if idx < len(df):
            row = df.iloc[idx]
            body_top = max(float(row["open"]), float(row["close"]))
            if price >= last_close >= body_top:
                return {"pass": True, "note": f"ราคาอยู่ในโซนแนวต้าน fractal ({body_top:.2f}-{price:.2f})"}
    
    for idx, price in reversed(piv_lows):
        if idx < len(df):
            row = df.iloc[idx]
            body_bottom = min(float(row["open"]), float(row["close"]))
            if body_bottom >= last_close >= price:
                return {"pass": True, "note": f"ราคาอยู่ในโซนแนวรับ fractal ({price:.2f}-{body_bottom:.2f})"}
    
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
    """RSI OVB/OVS"""
    if direction == "CALL" and rsi_val < 35:
        return {"pass": True, "note": f"RSI={rsi_val:.1f} oversold (<35)"}
    elif direction == "PUT" and rsi_val > 65:
        return {"pass": True, "note": f"RSI={rsi_val:.1f} overbought (>65)"}
    return {"pass": False, "note": f"RSI={rsi_val:.1f} ไม่ใช่ OVB/OVS"}


def _cond4_rsi_divergence(rsi: pd.Series, piv_highs, piv_lows, direction: str) -> dict:
    """RSI Divergence/Convergence at fractal S/R points"""
    if direction == "CALL":
        if len(piv_lows) >= 2:
            (i1, p1), (i2, p2) = piv_lows[-2], piv_lows[-1]
            r1, r2 = rsi.iloc[i1], rsi.iloc[i2]
            if p2 < p1 and r2 > r1:
                return {"pass": True, "note": f"Bullish Divergence: ราคา {p1:.2f}→{p2:.2f} (LL) RSI {r1:.1f}→{r2:.1f} (HL)"}
            if p2 <= p1 * 1.003 and r2 > r1:
                return {"pass": True, "note": f"Bullish Convergence: ราคา + RSI ยืนยันทิศขึ้น"}
    else:
        if len(piv_highs) >= 2:
            (i1, p1), (i2, p2) = piv_highs[-2], piv_highs[-1]
            r1, r2 = rsi.iloc[i1], rsi.iloc[i2]
            if p2 > p1 and r2 < r1:
                return {"pass": True, "note": f"Bearish Divergence: ราคา {p1:.2f}→{p2:.2f} (HH) RSI {r1:.1f}→{r2:.1f} (LH)"}
            if p2 >= p1 * 0.997 and r2 < r1:
                return {"pass": True, "note": f"Bearish Convergence: ราคา + RSI ยืนยันทิศลง"}
    
    return {"pass": False, "note": "ไม่พบ Divergence/Convergence"}


def _cond5_adx(adx_val: float) -> dict:
    """ADX > 20"""
    if adx_val >= 20:
        return {"pass": True, "note": f"ADX={adx_val:.1f} (>=20) เทรนแข็งแรง"}
    return {"pass": False, "note": f"ADX={adx_val:.1f} (<20) เทรนอ่อน"}


def _cond6_pa_confirmation(df: pd.DataFrame, direction: str) -> dict:
    """Price Action confirmation at S/R zone (pinbar/engulfing)"""
    n = len(df)
    for k in range(min(5, n)):
        idx = n - 1 - k
        if idx < 1:
            break
        cur = df.iloc[idx]
        prev = df.iloc[idx - 1]
        body = abs(cur["close"] - cur["open"])
        rng = max(cur["high"] - cur["low"], 1e-9)
        upper_w = cur["high"] - max(cur["close"], cur["open"])
        lower_w = min(cur["close"], cur["open"]) - cur["low"]
        
        if direction == "CALL":
            if (cur["close"] > cur["open"] and prev["close"] < prev["open"]
                    and cur["close"] >= prev["open"] and cur["open"] <= prev["close"]):
                return {"pass": True, "note": f"Bullish Engulfing (แท่งก่อน {k})"}
            if lower_w >= body * 1.5 and lower_w > 0:
                return {"pass": True, "note": f"Hammer ไส้ล่าง ≥1.5x (แท่งก่อน {k})"}
        else:
            if (cur["close"] < cur["open"] and prev["close"] > prev["open"]
                    and cur["close"] <= prev["open"] and cur["open"] >= prev["close"]):
                return {"pass": True, "note": f"Bearish Engulfing (แท่งก่อน {k})"}
            if upper_w >= body * 1.5 and upper_w > 0:
                return {"pass": True, "note": f"Shooting Star ไส้บน ≥1.5x (แท่งก่อน {k})"}
    
    return {"pass": False, "note": "ไม่พบ PA confirmation"}


def _cond7_fractal_trend(structure: str, direction: str) -> dict:
    """Trend from fractal swing high/low"""
    if direction == "CALL" and structure == "UPTREND":
        return {"pass": True, "note": f"Fractal: {structure} — HH/HL ตามเทรนขึ้น"}
    elif direction == "PUT" and structure == "DOWNTREND":
        return {"pass": True, "note": f"Fractal: {structure} — LH/LL ตามเทรนลง"}
    return {"pass": False, "note": f"Fractal: {structure} — ไม่ตรงทิศ {direction}"}


def _cond8_grip(ema200_price: float, cfg: dict) -> dict:
    """Grip (round numbers) near EMA200"""
    g = cfg.get("grip", {})
    if g.get("auto_scale", True):
        step = _nice_step(ema200_price / g.get("scale_divisor", 800))
    else:
        step = g.get("fixed_step", 5.0)
    
    line = round(ema200_price / step) * step
    dist_pct = abs(ema200_price - line) / ema200_price * 100.0
    tol = float(g.get("tolerance_pct", 0.05))
    
    if dist_pct <= tol:
        return {"pass": True, "note": f"EMA200 ({ema200_price:.2f}) ใกล้เลขกลม {line:.2f} ({dist_pct:.3f}%)"}
    return {"pass": False, "note": f"EMA200 ({ema200_price:.2f}) ห่างจากเลขกลม ({dist_pct:.3f}%)"}


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
    """BB squeeze or expansion"""
    cur_w = float(bb_width.iloc[-1]) if not np.isnan(bb_width.iloc[-1]) else 0
    avg_w = float(bb_width.rolling(20).mean().iloc[-1]) if len(bb_width) >= 20 else cur_w
    
    if cur_w > avg_w * 1.1:
        return {"pass": True, "note": f"BB ขยาย (width {cur_w:.2f}% > avg {avg_w:.2f}%) — มีวอลุ่ม"}
    elif cur_w < avg_w * 0.9:
        return {"pass": True, "note": f"BB บีบ (width {cur_w:.2f}% < avg {avg_w:.2f}%) — เตรียม breakout"}
    return {"pass": False, "note": f"BB ทรงตัว ({cur_w:.2f}% vs avg {avg_w:.2f}%)"}


def _cond10_mtf_trend(df: pd.DataFrame, direction: str) -> dict:
    """Multi-timeframe trend: M1, M30, H1, H4, D1 — need 3/5 TFs aligned"""
    close = df["close"]
    tf_configs = [
        ("M1", 1), ("M30", 30), ("H1", 60), ("H4", 240), ("D1", 1440)
    ]
    
    aligned_count = 0
    tf_results = []
    
    for tf_name, tf_minutes in tf_configs:
        try:
            resampled = close.resample(f"{tf_minutes}min", closed="left", label="last").last().dropna()
            if len(resampled) < 50:
                tf_results.append(f"{tf_name}: ข้อมูลไม่พอ")
                continue
            ema20 = resampled.ewm(span=20, adjust=False).mean()
            last_p = float(resampled.iloc[-1])
            last_e20 = float(ema20.iloc[-1])
            
            if direction == "CALL" and last_p > last_e20:
                aligned_count += 1
                tf_results.append(f"{tf_name}: ✅ขึ้น")
            elif direction == "PUT" and last_p < last_e20:
                aligned_count += 1
                tf_results.append(f"{tf_name}: ✅ลง")
            else:
                tf_results.append(f"{tf_name}: ❌ขัด")
        except Exception:
            tf_results.append(f"{tf_name}: error")
    
    passed = aligned_count >= 3
    return {"pass": passed, "note": f"MTF {aligned_count}/5 TFs ตรงทิศ ({', '.join(tf_results)})"}


# ══════════════════════════════════════════════════════════════════════════════
# EMA200 TOUCH Detection
# ══════════════════════════════════════════════════════════════════════════════
def _ema200_touch检测(df: pd.DataFrame, ema200: pd.Series,
                       lookback: int = 20) -> tuple[bool, str, str]:
    """ตรวจว่าแท่งล่าสุด (k=0) มี wick แตะ EMA200 หรือไม่
    Returns: (touched, note, touch_case)
    touch_case: WICK_TOUCH / CLOSE_TOUCH / ""
    """
    n = len(df)
    idx = n - 1
    if idx < 0:
        return False, "ไม่มีข้อมูล", ""

    row = df.iloc[idx]
    candle_high = float(row["high"])
    candle_low = float(row["low"])
    candle_close = float(row["close"])
    e_at_bar = float(ema200.iloc[idx]) if idx < len(ema200) else float(ema200.iloc[-1])
    e200 = float(ema200.iloc[-1])
    dist_now = abs(candle_close - e200) / e200 * 100.0

    if candle_low <= e_at_bar <= candle_high:
        if abs(candle_close - e200) / e200 * 100.0 <= 0.02:
            return True, f"ปิดตรง EMA200 ({e200:.2f})", "CLOSE_TOUCH"
        return True, f"wick แตะ EMA200 ({e200:.2f}, ห่าง {dist_now:.2f}%)", "WICK_TOUCH"

    return False, f"แท่งล่าสุดไม่ได้แตะ EMA200 ({e200:.2f})", ""


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SCORING FUNCTION
# ══════════════════════════════════════════════════════════════════════════════
def score_setup(
    df: pd.DataFrame,
    timeframe: str = "M5",
    target_hold_minutes: int = 30,
) -> SetupResult:
    cfg = load_config() or {}
    max_score = 10
    
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
    cond["c4_rsi_div"] = _cond4_rsi_divergence(rsi, piv_h, piv_l, direction)
    cond["c5_adx"] = _cond5_adx(adx_val)
    cond["c6_pa"] = _cond6_pa_confirmation(df, direction)
    cond["c7_fractal_trend"] = _cond7_fractal_trend(structure, direction)
    cond["c8_grip"] = _cond8_grip(e200, cfg)
    cond["c9_bb_width"] = _cond9_bb_width(bb_width)
    cond["c10_mtf"] = _cond10_mtf_trend(df, direction)
    
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
            "TICK_TOUCH": "⏱ ราคากดแตะ EMA200 ณ ขณะนี้",
            "WICK_TOUCH": "📉 Wick แตะ EMA200 (แท่งปิดห่าง)",
            "CLOSE_TOUCH": "📍 ปิดตรง EMA200",
        }
        touch_txt = touch_labels.get(touch_case, touch_note)
        note_parts = [
            f"🚨 IMPORTANCE 1 [{touch_case}]",
            f"{touch_txt} | EMA200 = {e200:.2f}",
            f"ผ่าน {passed_count}/10: {', '.join(passed_names) or 'none'}",
            f"เข้า {direction} | กรุณาสังเกตว่าเข้าจุดไหน winrate ดีสุด",
        ]

    elif crossed_ema100:
        # ═══ IMPORTANCE 2: EMA100 CROSSED → WAIT FOR 7/10 ═══
        importance = 2
        if passed_count >= 7:
            tier = "FIRE"
            entry_trigger = True
            note_parts = [
                f"⏳ IMPORTANCE 2 — ทะลุ EMA100 แล้ว + ผ่าน {passed_count}/10 เงื่อนไข",
                f"EMA100 = {e100:.2f} | EMA200 = {e200:.2f}",
                f"เข้า {direction} ตามเทรน {bias}",
            ]
        else:
            tier = "WATCH"
            entry_trigger = False
            note_parts = [
                f"⏳ IMPORTANCE 2 — ทะลุ EMA100 แล้ว แต่ผ่านแค่ {passed_count}/10 (ต้อง >=7)",
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
        conditions_total=10,
        conditions_log=cond,
        touch_case=touch_case if importance1 else "",
    )
