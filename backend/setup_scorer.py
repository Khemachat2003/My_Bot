"""
setup_scorer.py — V7: Owner's Actual Trading Setup
==================================================
Matches owner's real setup (70%+ winrate manually traded):

  Checklist:
    1. EMA200 TOUCH (HARD GATE): Price wick must touch EMA200 line — แตะครั้งเดียวพอ
    2. EMA TREND: EMA50/100/200 aligned + price above all 3 (uptrend) → pullback to EMA200
    3. ADX > 20: Trend is strong enough
    4. BB: Check if price breaks BB (not just squeeze)
    5. FRACTAL STRUCTURE: HH/HL = uptrend, LH/LL = downtrend
    6. REJECTION CANDLE: Pinbar/engulfing at EMA200 for confidence
    7. GRIP (Round Numbers): EMA200 near round number
    8. RSI DIVERGENCE/CONVERGENCE: Primary RSI signal

  Tier:
    FIRE  = EMA200 touch + trend + ADX + (RSI div OR rejection) + BB
    WATCH = EMA200 touch + trend + some confirm
    NONE  = no EMA200 touch or no trend
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
    max_score: int = 8
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


# ── Indicators ────────────────────────────────────────────────────────────────
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
    """HH+HL = UPTREND, LH+LL = DOWNTREND, else SIDEWAYS"""
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


# ── EMA200 TOUCH Detection ──────────────────────────────────────────────────
def _ema200_touch检测(df: pd.DataFrame, ema200: pd.Series, lookback: int = 20) -> tuple[bool, str]:
    """Check if price wick actually TOUCHES EMA200 line in last N candles.
    Touch = candle's low <= EMA200 <= candle's high"""
    n = len(df)
    touches = []
    for k in range(min(lookback, n)):
        idx = n - 1 - k
        if idx < 0:
            break
        row = df.iloc[idx]
        candle_high = float(row["high"])
        candle_low = float(row["low"])
        e_at_bar = float(ema200.iloc[idx]) if idx < len(ema200) else float(ema200.iloc[-1])
        if candle_low <= e_at_bar <= candle_high:
            touches.append(k)
    
    e200 = float(ema200.iloc[-1])
    if not touches:
        return False, f"ราคาไม่ได้แตะ EMA200 ({e200:.2f}) ใน {lookback} แท่ง"
    if touches[0] == 0:
        return True, f"ราคาแตะ EMA200 แล้ว! (แท่งล่าสุด wick ผ่าน {e200:.2f})"
    return True, f"ราคาเคยแตะ EMA200 ไป {touches[0]} แท่งก่อน (ล่าสุด {e200:.2f})"


# ── RSI Divergence / Convergence ─────────────────────────────────────────────
def _rsi_divergence(rsi: pd.Series, piv_highs, piv_lows, direction: str) -> tuple[float, str]:
    if direction == "CALL":
        if len(piv_lows) >= 2:
            (i1, p1), (i2, p2) = piv_lows[-2], piv_lows[-1]
            r1, r2 = rsi.iloc[i1], rsi.iloc[i2]
            if p2 < p1 and r2 > r1:
                return 1.0, f"Bullish Divergence: ราคา {p1:.2f}→{p2:.2f} (LL) แต่ RSI {r1:.1f}→{r2:.1f} (HL)"
            if p2 <= p1 * 1.003 and r2 > r1:
                return 0.8, f"Bullish Convergence: ราคา {p1:.2f}→{p2:.2f} + RSI {r1:.1f}→{r2:.1f}"
        r_now, r_prev = rsi.iloc[-1], rsi.iloc[-3]
        if r_now > r_prev and r_now < 45:
            return 0.6, f"RSI พลิกกลับ {r_prev:.1f}→{r_now:.1f} (oversold)"
        return 0.0, "ไม่พบ Bullish Divergence"
    else:
        if len(piv_highs) >= 2:
            (i1, p1), (i2, p2) = piv_highs[-2], piv_highs[-1]
            r1, r2 = rsi.iloc[i1], rsi.iloc[i2]
            if p2 > p1 and r2 < r1:
                return 1.0, f"Bearish Divergence: ราคา {p1:.2f}→{p2:.2f} (HH) แต่ RSI {r1:.1f}→{r2:.1f} (LH)"
            if p2 >= p1 * 0.997 and r2 < r1:
                return 0.8, f"Bearish Convergence: ราคา {p1:.2f}→{p2:.2f} + RSI {r1:.1f}→{r2:.1f}"
        r_now, r_prev = rsi.iloc[-1], rsi.iloc[-3]
        if r_now < r_prev and r_now > 55:
            return 0.6, f"RSI พลิกกลับ {r_prev:.1f}→{r_now:.1f} (overbought)"
        return 0.0, "ไม่พบ Bearish Divergence"


# ── Rejection Candle at EMA200 ───────────────────────────────────────────────
def _rejection_at_ema200(df: pd.DataFrame, ema200: pd.Series, direction: str, cfg: dict) -> tuple[float, str]:
    """Check for rejection candle (pinbar/engulfing) near EMA200."""
    tol = float(cfg.get("ema200_tol_pct", 0.15))
    lookback = int(cfg.get("rejection_lookback", 10))
    n = len(df)
    e200 = float(ema200.iloc[-1])
    
    for k in range(min(lookback, n)):
        idx = n - 1 - k
        if idx < 1:
            break
        cur = df.iloc[idx]
        prev = df.iloc[idx - 1]
        body = abs(cur["close"] - cur["open"])
        rng = max(cur["high"] - cur["low"], 1e-9)
        upper_w = cur["high"] - max(cur["close"], cur["open"])
        lower_w = min(cur["close"], cur["open"]) - cur["low"]
        
        # Check if candle is near EMA200
        e_at_bar = float(ema200.iloc[idx]) if idx < len(ema200) else e200
        near_ema = False
        if direction == "CALL":
            near_ema = float(cur["low"]) <= e_at_bar * (1 + tol / 100.0)
        else:
            near_ema = float(cur["high"]) >= e_at_bar * (1 - tol / 100.0)
        
        if not near_ema:
            continue
        
        if direction == "CALL":
            # Bullish engulfing
            if (cur["close"] > cur["open"] and prev["close"] < prev["open"]
                    and cur["close"] >= prev["open"] and cur["open"] <= prev["close"]):
                return 1.0, f"Bullish Engulfing ที่ EMA200 (แท่งก่อน {k})"
            # Hammer/Pinbar
            if lower_w >= body * 1.5 and lower_w > 0:
                return 1.0, f"Hammer ที่ EMA200 ไส้ล่าง ≥1.5x (แท่งก่อน {k})"
        else:
            # Bearish engulfing
            if (cur["close"] < cur["open"] and prev["close"] > prev["open"]
                    and cur["close"] <= prev["open"] and cur["open"] >= prev["close"]):
                return 1.0, f"Bearish Engulfing ที่ EMA200 (แท่งก่อน {k})"
            # Shooting star
            if upper_w >= body * 1.5 and upper_w > 0:
                return 1.0, f"Shooting Star ที่ EMA200 ไส้บน ≥1.5x (แท่งก่อน {k})"
    
    return 0.0, "ไม่พบ Rejection candle ที่ EMA200"


# ── Grip (Round Numbers) at EMA200 ──────────────────────────────────────────
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


def _grip_at_ema200(ema200_price: float, cfg: dict) -> tuple[bool, str]:
    """Check if EMA200 is near a round number (grip)."""
    g = cfg.get("grip", {})
    if g.get("auto_scale", True):
        step = _nice_step(ema200_price / g.get("scale_divisor", 800))
    else:
        step = g.get("fixed_step", 5.0)
    
    line = round(ema200_price / step) * step
    dist_pct = abs(ema200_price - line) / ema200_price * 100.0
    tol = float(g.get("tolerance_pct", 0.05))
    
    if dist_pct <= tol:
        return True, f"EMA200 ({ema200_price:.2f}) ใกล้เลขกลม {line:.2f} (ห่าง {dist_pct:.3f}%)"
    return False, f"EMA200 ({ema200_price:.2f}) ห่างจากเลขกลมที่ใกล้สุด {line:.2f} ({dist_pct:.3f}%)"


# ── Main Scoring Function ────────────────────────────────────────────────────
def score_setup(
    df: pd.DataFrame,
    timeframe: str = "M5",
    target_hold_minutes: int = 30,
) -> SetupResult:
    cfg = load_config() or {}
    max_score = 8
    
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
    bb_mid, bb_up, bb_lo, bb_width = _calc_bollinger_bands(close)
    adx = _calc_adx(high, low, close, 14)
    atr = _calc_atr(high, low, close, 14)
    
    frac_left = int(cfg.get("fractal", {}).get("left", 7))
    frac_right = int(cfg.get("fractal", {}).get("right", 7))
    piv_h, piv_l = _find_fractals(high, low, left=frac_left, right=frac_right)
    structure = _fractal_structure(piv_h, piv_l)
    
    last_close = float(close.iloc[-1])
    last_atr = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else float(close.tail(20).std() or 1.0)
    e50, e100, e200 = float(ema50.iloc[-1]), float(ema100.iloc[-1]), float(ema200.iloc[-1])
    adx_val = float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0
    rsi_val = float(rsi.iloc[-1])
    
    # ── Determine trend direction from EMA order ──
    trend_align_up = e50 > e100 > e200
    trend_align_down = e50 < e100 < e200
    
    if trend_align_up:
        direction, bias = "CALL", "BULLISH_TREND"
    elif trend_align_down:
        direction, bias = "PUT", "BEARISH_TREND"
    else:
        direction, bias = "", ""
    
    # No clear trend → NONE
    if not direction:
        dist200 = abs(last_close - e200) / e200 * 100.0
        return SetupResult(
            timeframe=timeframe,
            target_hold_minutes=target_hold_minutes,
            score=0.0, max_score=max_score, tier="NONE",
            direction="", bias="", entry_trigger=False,
            ema200_price=e200,
            dist200_pct=round(dist200, 4),
            near_ema200=False, touched_ema200=False,
            entry_trigger_note=(
                f"EMA ไม่เรียงตามเทรน (EMA50 {e50:.2f} / EMA100 {e100:.2f} / EMA200 {e200:.2f}) "
                f"— รอเทรนชัดเจนก่อน"),
            details={
                "ema_trend": {"ok": False, "frac": 0.0, "weight": 1, "note": "EMA ไม่เรียงตามทิศ"},
            },
        )
    
    # ════════════════════════════════════════════════════════════════════════
    # CHECKLIST ITEMS
    # ════════════════════════════════════════════════════════════════════════
    
    details = {}
    score = 0.0
    
    # 1) EMA200 TOUCH (HARD GATE) ──────────────────────────────────────────
    touched, touch_note = _ema200_touch检测(df, ema200, lookback=20)
    dist200 = abs(last_close - e200) / e200 * 100.0
    near_ema200 = dist200 <= float(cfg.get("ema200_near_tol_pct", 0.20))
    
    if not touched:
        return SetupResult(
            timeframe=timeframe,
            target_hold_minutes=target_hold_minutes,
            score=0.0, max_score=max_score, tier="NONE",
            direction=direction, bias=bias, entry_trigger=False,
            ema200_price=e200,
            dist200_pct=round(dist200, 4),
            near_ema200=near_ema200, touched_ema200=False,
            entry_trigger_note=(
                f"❌ ราคา {last_close:.2f} ไม่ได้แตะ EMA200 {e200:.2f} ({dist200:.2f}%) "
                f"— ใจหลักไม่ผ่าน (ต้องแตะ EMA200)"),
            details={"ema200_touch": {"ok": False, "frac": 0.0, "weight": 1, "note": touch_note}},
        )
    
    details["ema200_touch"] = {"ok": True, "frac": 1.0, "weight": 1, "note": touch_note}
    score += 1.0
    
    # 2) EMA TREND (EMA50/100/200 aligned + price above all) ──────────────
    ema_trend_note = f"EMA50 {e50:.2f} > EMA100 {e100:.2f} > EMA200 {e200:.2f}" if trend_align_up else \
                     f"EMA50 {e50:.2f} < EMA100 {e100:.2f} < EMA200 {e200:.2f}"
    # Check if price was above all 3 then pulled back to EMA200
    look = min(30, len(close))
    if direction == "CALL":
        was_above = float(close.iloc[-look:].max()) > e50
        pulled_back = last_close <= e50
    else:
        was_above = float(close.iloc[-look:].min()) < e50
        pulled_back = last_close >= e50
    
    if was_above and pulled_back:
        ema_trend_frac = 1.0
        ema_trend_note += " + ย่อมาหา EMA200 แล้ว"
    elif trend_align_up or trend_align_down:
        ema_trend_frac = 0.7
        ema_trend_note += " (ยังไม่确认 pullback)"
    else:
        ema_trend_frac = 0.0
    
    details["ema_trend"] = {"ok": ema_trend_frac >= 0.5, "frac": ema_trend_frac, "weight": 1, "note": ema_trend_note}
    score += ema_trend_frac
    
    # 3) ADX > 20 ─────────────────────────────────────────────────────────
    adx_min = float(cfg.get("adx_min", 20))
    if adx_val >= adx_min:
        adx_frac = 1.0
    elif adx_val >= adx_min - 5:
        adx_frac = 0.5
    else:
        adx_frac = 0.0
    details["adx"] = {"ok": adx_frac >= 0.5, "frac": adx_frac, "weight": 1, "note": f"ADX={adx_val:.1f} (>= {adx_min:.0f})"}
    score += adx_frac
    
    # 4) BB — ราคาทะลุ BB หรือไม่ ─────────────────────────────────────────
    last_bb_up = float(bb_up.iloc[-1]) if not np.isnan(bb_up.iloc[-1]) else last_close + last_atr
    last_bb_lo = float(bb_lo.iloc[-1]) if not np.isnan(bb_lo.iloc[-1]) else last_close - last_atr
    last_bb_width = float(bb_width.iloc[-1]) if not np.isnan(bb_width.iloc[-1]) else 0.0
    avg_bb_width = float(bb_width.rolling(20).mean().iloc[-1]) if len(bb_width) >= 20 else last_bb_width
    
    if direction == "CALL":
        # ราคาทะลุ BB ล่าง = oversold + มีแรงดีดกลับ
        if last_close <= last_bb_lo:
            bb_frac = 1.0
            bb_note = f"ราคา {last_close:.2f} ทะลุ BB ล่าง {last_bb_lo:.2f} — oversold + มีแรงดีด"
        elif last_close < last_bb_lo * 1.005:
            bb_frac = 0.7
            bb_note = f"ราคา {last_close:.2f} ใกล้ BB ล่าง {last_bb_lo:.2f}"
        else:
            bb_frac = 0.3
            bb_note = f"ราคา {last_close:.2f} อยู่ใน BB ({last_bb_lo:.2f}-{last_bb_up:.2f})"
    else:
        # ราคาทะลุ BB บน = overbought + มีแรงกดกลับ
        if last_close >= last_bb_up:
            bb_frac = 1.0
            bb_note = f"ราคา {last_close:.2f} ทะลุ BB บน {last_bb_up:.2f} — overbought + มีแรงกด"
        elif last_close > last_bb_up * 0.995:
            bb_frac = 0.7
            bb_note = f"ราคา {last_close:.2f} ใกล้ BB บน {last_bb_up:.2f}"
        else:
            bb_frac = 0.3
            bb_note = f"ราคา {last_close:.2f} อยู่ใน BB ({last_bb_lo:.2f}-{last_bb_up:.2f})"
    
    details["bb"] = {"ok": bb_frac >= 0.5, "frac": bb_frac, "weight": 1, "note": bb_note}
    score += bb_frac
    
    # 5) FRACTAL STRUCTURE (HH/HL/LH/LL) ──────────────────────────────────
    if direction == "CALL":
        struct_ok = structure == "UPTREND"
        struct_note = f"Fractal: {structure} — HH/HL ตามเทรนขึ้น" if struct_ok else f"Fractal: {structure}"
    else:
        struct_ok = structure == "DOWNTREND"
        struct_note = f"Fractal: {structure} — LH/LL ตามเทรนลง" if struct_ok else f"Fractal: {structure}"
    struct_frac = 1.0 if struct_ok else 0.0
    details["fractal"] = {"ok": struct_ok, "frac": struct_frac, "weight": 1, "note": struct_note}
    score += struct_frac
    
    # 6) REJECTION CANDLE at EMA200 ────────────────────────────────────────
    rej_frac, rej_note = _rejection_at_ema200(df, ema200, direction, cfg)
    details["rejection"] = {"ok": rej_frac >= 0.5, "frac": rej_frac, "weight": 1, "note": rej_note}
    score += rej_frac
    
    # 7) GRIP (Round Numbers) at EMA200 ───────────────────────────────────
    grip_ok, grip_note = _grip_at_ema200(e200, cfg)
    grip_frac = 1.0 if grip_ok else 0.0
    details["grip"] = {"ok": grip_ok, "frac": grip_frac, "weight": 1, "note": grip_note}
    score += grip_frac
    
    # 8) RSI DIVERGENCE/CONVERGENCE ────────────────────────────────────────
    rsi_frac, rsi_note = _rsi_divergence(rsi, piv_h, piv_l, direction)
    details["rsi_div"] = {"ok": rsi_frac >= 0.5, "frac": rsi_frac, "weight": 1, "note": rsi_note}
    score += rsi_frac
    
    # ════════════════════════════════════════════════════════════════════════
    # TIER DETERMINATION
    # ════════════════════════════════════════════════════════════════════════
    
    fire_score = float(cfg.get("fire_score", 6))
    watch_score = float(cfg.get("watch_score", 4))
    
    has_strong_confirm = (rsi_frac >= 0.5 or rej_frac >= 0.5)  # RSI div OR rejection
    has_trend = ema_trend_frac >= 0.5
    has_adx = adx_frac >= 0.5
    has_bb = bb_frac >= 0.5
    has_fractal = struct_frac >= 0.5
    
    if score >= fire_score and has_trend and has_adx and has_strong_confirm:
        tier = "FIRE"
        entry_trigger = True
    elif score >= watch_score and has_trend:
        tier = "WATCH"
        entry_trigger = False
    else:
        tier = "NONE"
        entry_trigger = False
    
    note_parts = [f"Setup {score:.1f}/{max_score} → {tier}"]
    if tier == "FIRE":
        note_parts.append(
            f"✅ ราคาแตะ EMA200 {e200:.2f} + เทรน {direction} + ADX={adx_val:.0f} "
            f"+ {rsi_note} + {rej_note}")
    elif tier == "WATCH":
        note_parts.append(f"⏳ รอ confirm เพิ่ม ({rsi_note} | {rej_note})")
    else:
        note_parts.append(f"❌ สกอร์ {score:.1f} ต่ำกว่าเกณฑ์ ({fire_score:.0f})")
    
    score_breakdown = {name: round(d["weight"] * d["frac"], 2) for name, d in details.items()}
    
    return SetupResult(
        timeframe=timeframe,
        target_hold_minutes=target_hold_minutes,
        score=round(score, 2),
        max_score=max_score,
        tier=tier,
        direction=direction,
        bias=bias,
        entry_trigger=entry_trigger,
        entry_trigger_note=" | ".join(note_parts),
        details=details,
        grip_hits=["Grip"] if grip_ok else [],
        score_breakdown=score_breakdown,
        model_prob=None,
        ema200_price=e200,
        dist200_pct=round(dist200, 4),
        near_ema200=near_ema200,
        touched_ema200=True,
    )
