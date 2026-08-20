"""
setup_scorer.py — V6: Simple Setup Matching Owner's Actual Trading
================================================================
Simplified to match the owner's real trading setup (70%+ winrate):

  3 Core Pillars:
    1. EMA200 TOUCH: Price wick must actually touch EMA200 line
    2. Fractal 15 S/R: Williams Fractal (7 left, 1 center, 7 right) → S/R zones
    3. RSI Divergence/Convergence: Primary RSI signal

  Rules:
    - FIRE: EMA200 touch + trend aligned + RSI divergence (CALL/PUT)
    - WATCH: Near EMA200 but no divergence yet
    - NONE: Price far from EMA200 or no trend

  Binary Options specific: Fixed payout ~82%, fixed expiry
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
    """Load config with cache by mtime"""
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
    max_score: int = 3
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


def _calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


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
    """Williams Fractal: center candle must be highest/lowest in [i-left, i+right]
    Returns (piv_highs, piv_lows) = [(index, price), ...]"""
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


# ── EMA200 TOUCH Detection ──────────────────────────────────────────────────
def _ema200_touch检测(df: pd.DataFrame, ema200: pd.Series, direction: str, lookback: int = 20) -> tuple[bool, str]:
    """Check if price wick actually TOUCHES EMA200 line in last N candles.
    Touch = candle's low <= EMA200 <= candle's high (for CALL)
           or candle's high >= EMA200 >= candle's low (for PUT)
    Returns (is_touched, note)"""
    e200 = float(ema200.iloc[-1])
    n = len(df)
    
    touches = []
    for k in range(min(lookback, n)):
        idx = n - 1 - k
        if idx < 0:
            break
        row = df.iloc[idx]
        candle_high = float(row["high"])
        candle_low = float(row["low"])
        e_at_bar = float(ema200.iloc[idx]) if idx < len(ema200) else e200
        
        # Wick touches EMA200: low <= EMA200 <= high
        if candle_low <= e_at_bar <= candle_high:
            touches.append(k)
    
    if not touches:
        return False, f"ราคาไม่ได้แตะ EMA200 ({e200:.2f}) ใน {lookback} แท่ง"
    
    if touches[0] == 0:
        return True, f"ราคาแตะ EMA200 แล้ว! (แท่งล่าสุด wick ผ่าน {e200:.2f})"
    else:
        return True, f"ราคาเคยแตะ EMA200 ไป {touches[0]} แท่งก่อน (ล่าสุด {e200:.2f})"


# ── RSI Divergence / Convergence ─────────────────────────────────────────────
def _rsi_divergence(rsi: pd.Series, piv_highs, piv_lows, direction: str) -> tuple[float, str]:
    """Detect RSI Divergence/Convergence using fractal pivot points.
    - Bullish Divergence: Price makes LL but RSI makes HL ( CALL signal)
    - Bearish Divergence: Price makes HH but RSI makes LH (PUT signal)
    - Convergence: Price and RSI confirm each other"""
    
    if direction == "CALL":
        # Look for bullish divergence at recent lows
        if len(piv_lows) >= 2:
            (i1, p1), (i2, p2) = piv_lows[-2], piv_lows[-1]
            r1, r2 = rsi.iloc[i1], rsi.iloc[i2]
            if p2 < p1 and r2 > r1:
                return 1.0, f"Bullish Divergence: ราคา {p1:.2f}→{p2:.2f} (LL) แต่ RSI {r1:.1f}→{r2:.1f} (HL)"
            if p2 <= p1 * 1.003 and r2 > r1:
                return 0.8, f"Bullish Convergence: ราคา {p1:.2f}→{p2:.2f} (สมดุล) + RSI {r1:.1f}→{r2:.1f} (สูงขึ้น)"
        
        # Fallback: RSI oversold and turning up
        r_now, r_prev = rsi.iloc[-1], rsi.iloc[-3]
        if r_now > r_prev and r_now < 45:
            return 0.6, f"RSI เริ่มพลิกกลับ {r_prev:.1f}→{r_now:.1f} (จาก oversold)"
        return 0.0, "ไม่พบ Bullish Divergence/Convergence"
    
    else:  # PUT
        # Look for bearish divergence at recent highs
        if len(piv_highs) >= 2:
            (i1, p1), (i2, p2) = piv_highs[-2], piv_highs[-1]
            r1, r2 = rsi.iloc[i1], rsi.iloc[i2]
            if p2 > p1 and r2 < r1:
                return 1.0, f"Bearish Divergence: ราคา {p1:.2f}→{p2:.2f} (HH) แต่ RSI {r1:.1f}→{r2:.1f} (LH)"
            if p2 >= p1 * 0.997 and r2 < r1:
                return 0.8, f"Bearish Convergence: ราคา {p1:.2f}→{p2:.2f} (สมดุล) + RSI {r1:.1f}→{r2:.1f} (ต่ำลง)"
        
        # Fallback: RSI overbought and turning down
        r_now, r_prev = rsi.iloc[-1], rsi.iloc[-3]
        if r_now < r_prev and r_now > 55:
            return 0.6, f"RSI เริ่มพลิกกลับ {r_prev:.1f}→{r_now:.1f} (จาก overbought)"
        return 0.0, "ไม่พบ Bearish Divergence/Convergence"


# ── S/R Zones from Fractal 15 ────────────────────────────────────────────────
def _fractal_sr_zones(df: pd.DataFrame, piv_highs, piv_lows, direction: str) -> tuple[float, str]:
    """S/R zones based on user's method:
    - Fractal high → Resistance zone (wick tip to body open)
    - Fractal low → Support zone (wick tip to body open)
    Check if current price is near any zone."""
    
    last_close = float(df["close"].iloc[-1])
    last_low = float(df["low"].iloc[-1])
    last_high = float(df["high"].iloc[-1])
    
    # Check resistance zones (fractal highs)
    for idx, price in reversed(piv_highs):
        if idx < len(df):
            row = df.iloc[idx]
            body_top = max(float(row["open"]), float(row["close"]))
            # Zone = from fractal high (wick tip) down to body top
            zone_high = price
            zone_low = body_top
            if zone_high >= last_close >= zone_low:
                return 1.0, f"ราคาอยู่ในโซนแนวต้าน fractal ({zone_low:.2f}-{zone_high:.2f})"
            if abs(last_close - zone_high) / last_close * 100 < 0.15:
                return 0.8, f"ราคาใกล้โซนแนวต้าน fractal ({zone_high:.2f})"
    
    # Check support zones (fractal lows)
    for idx, price in reversed(piv_lows):
        if idx < len(df):
            row = df.iloc[idx]
            body_bottom = min(float(row["open"]), float(row["close"]))
            # Zone = from fractal low (wick tip) up to body bottom
            zone_high = body_bottom
            zone_low = price
            if zone_high >= last_close >= zone_low:
                return 1.0, f"ราคาอยู่ในโซนแนวรับ fractal ({zone_low:.2f}-{zone_high:.2f})"
            if abs(last_close - zone_low) / last_close * 100 < 0.15:
                return 0.8, f"ราคาใกล้โซนแนวรับ fractal ({zone_low:.2f})"
    
    return 0.0, "ราคาไม่ได้อยู่ในโซน S/R จาก fractal"


# ── Main Scoring Function ────────────────────────────────────────────────────
def score_setup(
    df: pd.DataFrame,
    timeframe: str = "M5",
    target_hold_minutes: int = 30,
) -> SetupResult:
    """Simplified scoring matching owner's actual trading setup.
    
    3 Core Pillars:
        1. EMA200 Touch (hard gate)
        2. Fractal 15 S/R zones
        3. RSI Divergence/Convergence
    
    Max score = 3 (one point per pillar)
    FIRE = score >= 2.5 (all 3 pillars strong)
    WATCH = score >= 1.5 (2 pillars)
    NONE = score < 1.5
    """
    cfg = load_config() or {}
    max_score = 3
    
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
    adx = _calc_adx(high, low, close, 14)
    
    # Fractal 15 (7 left, 1 center, 7 right)
    frac_left = int(cfg.get("fractal", {}).get("left", 7))
    frac_right = int(cfg.get("fractal", {}).get("right", 7))
    piv_h, piv_l = _find_fractals(high, low, left=frac_left, right=frac_right)
    
    last_close = float(close.iloc[-1])
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
    
    # No clear trend → NONE (don't trade against trend)
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
                f"— รอเทรนชัดเจนก่อน ไม่เทรดสวนเทรน"),
            details={
                "trend": {"ok": False, "frac": 0.0, "weight": 1,
                          "note": "EMA ไม่เรียงตามทิศเทรน"},
            },
        )
    
    # ── Pillar 1: EMA200 Touch (HARD GATE) ──
    touched, touch_note = _ema200_touch检测(df, ema200, direction, lookback=20)
    dist200 = abs(last_close - e200) / e200 * 100.0
    near_ema200 = dist200 <= float(cfg.get("ema200_near_tol_pct", 0.20))
    
    # Hard gate: MUST touch EMA200 to fire
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
                f"— ใจหลักของระบบไม่ผ่าน (ต้องแตะ EMA200 เท่านั้น)"),
            details={
                "ema200_touch": {"ok": False, "frac": 0.0, "weight": 1, "note": touch_note},
            },
        )
    
    # ── Pillar 2: Fractal 15 S/R Zones ──
    sr_frac, sr_note = _fractal_sr_zones(df, piv_h, piv_l, direction)
    
    # ── Pillar 3: RSI Divergence/Convergence ──
    rsi_frac, rsi_note = _rsi_divergence(rsi, piv_h, piv_l, direction)
    
    # ── Calculate total score ──
    # Pillar 1: EMA200 touch = 1.0 (already passed hard gate)
    # Pillar 2: S/R zones = 0.0 to 1.0
    # Pillar 3: RSI divergence = 0.0 to 1.0
    score = 1.0 + sr_frac + rsi_frac
    
    details = {
        "ema200_touch": {"ok": True, "frac": 1.0, "weight": 1, "note": touch_note},
        "fractal_sr": {"ok": sr_frac >= 0.5, "frac": round(sr_frac, 2), "weight": 1, "note": sr_note},
        "rsi_divergence": {"ok": rsi_frac >= 0.5, "frac": round(rsi_frac, 2), "weight": 1, "note": rsi_note},
    }
    
    # ── Tier Determination ──
    # FIRE: All 3 pillars strong (EMA200 touch + S/R zone + RSI divergence)
    # WATCH: EMA200 touch + at least one of (S/R or RSI)
    # NONE: Only EMA200 touch but no confirmation
    
    if score >= 2.5:
        tier = "FIRE"
        entry_trigger = True
        note_parts = [
            f"✅ FIRE! Setup {score:.1f}/{max_score}",
            f"ราคาแตะ EMA200 {e200:.2f} + {sr_note} + {rsi_note}",
            f"เข้า {direction} ตามเทรน {bias}",
        ]
    elif score >= 1.5:
        tier = "WATCH"
        entry_trigger = False
        note_parts = [
            f"⏳ WATCH: Setup {score:.1f}/{max_score}",
            f"ราคาแตะ EMA200 แล้วแต่ยังไม่มี confirm ครบ",
            f"{sr_note} | {rsi_note}",
        ]
    else:
        tier = "NONE"
        entry_trigger = False
        note_parts = [
            f"❌ NONE: Setup {score:.1f}/{max_score}",
            f"ราคาแตะ EMA200 แล้วแต่ไม่มี S/R zone หรือ RSI divergence",
            f"{sr_note} | {rsi_note}",
        ]
    
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
        grip_hits=[],
        score_breakdown=score_breakdown,
        model_prob=None,
        ema200_price=e200,
        dist200_pct=round(dist200, 4),
        near_ema200=near_ema200,
        touched_ema200=True,
    )
