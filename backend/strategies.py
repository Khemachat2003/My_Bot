"""
strategies.py — 3 Strategies สำหรับ XAUUSD

Strategy 1: EMA Trend + RSI Pullback
  - EMA20 > EMA50 > EMA200 (uptrend) หรือกลับกัน
  - RSI pullback กลับมาที่ 40-50 zone
  - MACD histogram เริ่มกลับทิศ

Strategy 2: RSI Oversold/Overbought + MACD Cross
  - RSI < 30 (oversold) → BUY, RSI > 70 (overbought) → SELL
  - MACD cross เป็น confirmation
  - ADX > 20 (มีแนวโน้มชัด)

Strategy 3: Bollinger Band Squeeze + Breakout
  - BB width แคบ (squeeze) → รอ breakout
  - ราคา break บน/ล่าง band พร้อม volume สูง
  - EMA เป็น trend filter
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Signal:
    direction: Literal["BUY", "SELL", "NONE"] = "NONE"
    entry:     float = 0.0
    sl:        float = 0.0
    tp1:       float = 0.0
    tp2:       float = 0.0
    strategy:  str   = ""
    reason:    str   = ""
    atr:       float = 0.0


# ─── Strategy 1: EMA Trend + RSI Pullback ────────────────────────────────────

def strategy_ema_rsi(row: pd.Series, prev: pd.Series) -> Signal:
    """
    BUY:  EMA20 > EMA50 > EMA200, RSI 35-55, MACD hist เพิ่ม
    SELL: EMA20 < EMA50 < EMA200, RSI 45-65, MACD hist ลด
    SL:   1.5x ATR จาก entry
    TP:   2x ATR (TP1), 3.5x ATR (TP2)
    """
    atr_val = row["atr"]
    if atr_val == 0 or pd.isna(atr_val):
        return Signal()

    # ─ BUY condition ─
    bull_trend = (row["ema_20"] > row["ema_50"]) and (row["ema_50"] > row["ema_200"])
    rsi_zone   = 35 <= row["rsi"] <= 55
    macd_up    = row["macd_hist"] > prev["macd_hist"]  # histogram กำลังเพิ่ม
    adx_ok     = row["adx"] > 20

    if bull_trend and rsi_zone and macd_up and adx_ok:
        entry = row["close"]
        sl    = entry - 1.5 * atr_val
        return Signal(
            direction="BUY", entry=entry,
            sl=sl, tp1=entry + 2.0 * atr_val, tp2=entry + 3.5 * atr_val,
            strategy="EMA_RSI", atr=atr_val,
            reason=f"Uptrend | RSI:{row['rsi']:.1f} | ADX:{row['adx']:.1f}"
        )

    # ─ SELL condition ─
    bear_trend = (row["ema_20"] < row["ema_50"]) and (row["ema_50"] < row["ema_200"])
    rsi_zone_s = 45 <= row["rsi"] <= 65
    macd_down  = row["macd_hist"] < prev["macd_hist"]

    if bear_trend and rsi_zone_s and macd_down and adx_ok:
        entry = row["close"]
        sl    = entry + 1.5 * atr_val
        return Signal(
            direction="SELL", entry=entry,
            sl=sl, tp1=entry - 2.0 * atr_val, tp2=entry - 3.5 * atr_val,
            strategy="EMA_RSI", atr=atr_val,
            reason=f"Downtrend | RSI:{row['rsi']:.1f} | ADX:{row['adx']:.1f}"
        )

    return Signal()


# ─── Strategy 2: RSI Extreme + MACD Cross ────────────────────────────────────

def strategy_rsi_macd(row: pd.Series, prev: pd.Series) -> Signal:
    """
    BUY:  RSI < 32, MACD cross up (macd > signal และ prev macd < prev signal)
    SELL: RSI > 68, MACD cross down
    SL:   recent swing low/high หรือ 2x ATR
    TP:   BB mid (TP1), BB upper/lower (TP2)
    """
    atr_val = row["atr"]
    if atr_val == 0 or pd.isna(atr_val):
        return Signal()

    # MACD cross
    macd_cross_up   = (row["macd_line"] > row["macd_signal"]) and \
                      (prev["macd_line"] <= prev["macd_signal"])
    macd_cross_down = (row["macd_line"] < row["macd_signal"]) and \
                      (prev["macd_line"] >= prev["macd_signal"])

    # BUY
    if row["rsi"] < 32 and macd_cross_up:
        entry = row["close"]
        sl    = entry - 2.0 * atr_val
        return Signal(
            direction="BUY", entry=entry,
            sl=sl, tp1=row["bb_mid"], tp2=row["bb_upper"],
            strategy="RSI_MACD", atr=atr_val,
            reason=f"RSI oversold:{row['rsi']:.1f} | MACD cross up"
        )

    # SELL
    if row["rsi"] > 68 and macd_cross_down:
        entry = row["close"]
        sl    = entry + 2.0 * atr_val
        return Signal(
            direction="SELL", entry=entry,
            sl=sl, tp1=row["bb_mid"], tp2=row["bb_lower"],
            strategy="RSI_MACD", atr=atr_val,
            reason=f"RSI overbought:{row['rsi']:.1f} | MACD cross down"
        )

    return Signal()


# ─── Strategy 3: Bollinger Squeeze Breakout ───────────────────────────────────

def strategy_bb_breakout(row: pd.Series, prev: pd.Series,
                          squeeze_threshold: float = 1.5) -> Signal:
    """
    Squeeze: BB width < threshold %
    Breakout BUY:  ราคา close เหนือ upper band + volume สูง + EMA20 > EMA50
    Breakout SELL: ราคา close ต่ำกว่า lower band + volume สูง + EMA20 < EMA50
    """
    atr_val = row["atr"]
    if atr_val == 0 or pd.isna(atr_val):
        return Signal()

    # Squeeze condition (bb_width ก่อนหน้าแคบ)
    prev_squeeze = prev["bb_width"] < squeeze_threshold

    # Volume spike (volume สูงกว่า average)
    # (ใช้ bb_width เป็น proxy เพราะไม่มี volume rolling ใน row เดี่ยว)
    bb_expanding = row["bb_width"] > prev["bb_width"] * 1.1

    # BUY Breakout
    if (prev_squeeze and
        row["close"] > row["bb_upper"] and
        bb_expanding and
        row["ema_20"] > row["ema_50"]):
        entry = row["close"]
        sl    = row["bb_mid"]
        tp1   = entry + 1.5 * atr_val
        tp2   = entry + 3.0 * atr_val
        return Signal(
            direction="BUY", entry=entry, sl=sl, tp1=tp1, tp2=tp2,
            strategy="BB_BREAKOUT", atr=atr_val,
            reason=f"BB Squeeze breakout UP | width:{row['bb_width']:.2f}%"
        )

    # SELL Breakout
    if (prev_squeeze and
        row["close"] < row["bb_lower"] and
        bb_expanding and
        row["ema_20"] < row["ema_50"]):
        entry = row["close"]
        sl    = row["bb_mid"]
        tp1   = entry - 1.5 * atr_val
        tp2   = entry - 3.0 * atr_val
        return Signal(
            direction="SELL", entry=entry, sl=sl, tp1=tp1, tp2=tp2,
            strategy="BB_BREAKOUT", atr=atr_val,
            reason=f"BB Squeeze breakout DOWN | width:{row['bb_width']:.2f}%"
        )

    return Signal()


# ─── Combined Signal (ใช้ทั้ง 3 strategies) ────────────────────────────────

def get_signal(row: pd.Series, prev: pd.Series,
               enabled: list[str] = None) -> Signal:
    """
    รวม signal จากทุก strategy
    ถ้าหลาย strategy ให้สัญญาณเดียวกัน = confidence สูงขึ้น
    """
    enabled = enabled or ["EMA_RSI", "RSI_MACD", "BB_BREAKOUT"]
    signals = []

    if "EMA_RSI" in enabled:
        s = strategy_ema_rsi(row, prev)
        if s.direction != "NONE":
            signals.append(s)

    if "RSI_MACD" in enabled:
        s = strategy_rsi_macd(row, prev)
        if s.direction != "NONE":
            signals.append(s)

    if "BB_BREAKOUT" in enabled:
        s = strategy_bb_breakout(row, prev)
        if s.direction != "NONE":
            signals.append(s)

    if not signals:
        return Signal()

    # ถ้า signal ขัดแย้งกัน (BUY + SELL) → ไม่เข้า
    directions = set(s.direction for s in signals)
    if len(directions) > 1:
        return Signal()

    # เลือก signal ที่ดีที่สุด (R:R สูงสุด)
    def rr(s: Signal) -> float:
        risk   = abs(s.entry - s.sl)
        reward = abs(s.tp2 - s.entry)
        return reward / risk if risk > 0 else 0

    best = max(signals, key=rr)
    if len(signals) > 1:
        best.reason += f" [CONFLUENCE x{len(signals)}]"
    return best
