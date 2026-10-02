"""Characterization tests — backend/setup_scorer.py

ล็อกพฤติกรรม Two-Tier 11-Checklist scoring ด้วยข้อมูล synthetic:
  - classify_ema200_touch (classifier กลาง — pure function)
  - score_setup: tier/importance/direction ตามเงื่อนไข EMA
ข้อมูลสร้างแบบ deterministic ทุกเคส ไม่ดึงเน็ต ไม่แตะ DB
"""
import numpy as np
import pandas as pd

from backend.setup_scorer import classify_ema200_touch, score_setup


# ── helpers ──────────────────────────────────────────────────────────────────
def mk_df(closes, highs=None, lows=None, opens=None, start="2026-08-10 10:00"):
    """สร้าง DataFrame OHLC จากราคา close (high/low/open คงที่ ±0.5 ถ้าไม่กำหนด)"""
    closes = [float(c) for c in closes]
    highs = highs or [c + 0.5 for c in closes]
    lows = lows or [c - 0.5 for c in closes]
    opens = opens or [c for c in closes]
    idx = pd.date_range(start, periods=len(closes), freq="1min", tz="UTC")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes}, index=idx)


def ema(series, span):
    """EMA สูตรเดียวกับ _calc_ema ใน setup_scorer (ewm span, adjust=False)"""
    return series.ewm(span=span, adjust=False).mean()


def flat_then_rise(base=2400.0, flat_bars=220, rise_bars=90, rise_to=2520.0):
    """ชุดข้อมูล: แบนราบที่ base แล้วไต่ขึ้นเป็นเส้นตรงไป rise_to
    → EMA50 > EMA100 > EMA200 = ทิศ CALL ตามเทรน"""
    closes = [base] * flat_bars
    step = (rise_to - base) / rise_bars
    closes += [base + step * (i + 1) for i in range(rise_bars)]
    return mk_df(closes)


# ── classify_ema200_touch (classifier กลาง) ──────────────────────────────────
def test_classify_touch_when_line_in_range():
    touched, case, note, direction = classify_ema200_touch(
        c_open=2400.2, c_high=2401.0, c_low=2399.0, c_close=2400.5, e200=2400.0)
    assert touched is True
    assert direction == "CALL"


def test_classify_no_touch():
    touched, case, note, direction = classify_ema200_touch(
        c_open=2402.0, c_high=2404.0, c_low=2401.5, c_close=2403.0, e200=2400.0)
    assert touched is False
    assert case == ""
    assert direction == ""


def test_classify_breakout_case():
    # เปิดใต้เส้น ปิดเหนือเส้น + dist(close→เส้น) ≥ ½body → BREAKOUT
    touched, case, note, direction = classify_ema200_touch(
        c_open=2395.0, c_high=2406.0, c_low=2394.0, c_close=2405.0, e200=2400.0)
    assert touched is True
    assert case == "BREAKOUT"
    assert direction == "CALL"


def test_classify_wick_bounce_case():
    # wick ลงแตะเส้นแล้วปิดกลับเหนือเส้น
    touched, case, note, direction = classify_ema200_touch(
        c_open=2400.2, c_high=2401.0, c_low=2399.0, c_close=2400.8, e200=2400.0)
    assert touched is True
    assert case == "WICK_BOUNCE"
    assert direction == "CALL"


def test_classify_tick_touch_when_doji():
    # body = 0 (doji) → ไม่เข้า BREAKOUT/WICK_BOUNCE → TICK_TOUCH
    touched, case, note, direction = classify_ema200_touch(
        c_open=2400.05, c_high=2400.5, c_low=2399.5, c_close=2400.05, e200=2400.0)
    assert touched is True
    assert case == "TICK_TOUCH"


def test_classify_direction_put_when_close_below_line():
    touched, case, note, direction = classify_ema200_touch(
        c_open=2400.5, c_high=2401.0, c_low=2399.0, c_close=2399.6, e200=2400.0)
    assert touched is True
    assert direction == "PUT"


def test_classify_invalid_ema():
    touched, case, note, direction = classify_ema200_touch(
        c_open=1.0, c_high=2.0, c_low=0.5, c_close=1.5, e200=0.0)
    assert touched is False


# ── score_setup ──────────────────────────────────────────────────────────────
def test_score_setup_short_data_returns_none_tier():
    df = mk_df([2400.0] * 100)
    res = score_setup(df, timeframe="M5")
    assert res.tier == "NONE"
    assert res.entry_trigger is False
    assert res.max_score == 11
    # note แจ้งว่าต้องการ ≥210 แท่ง
    assert "210" in res.details["Data"]["note"]


def test_score_setup_uptrend_far_above_is_none():
    """ไต่ขึ้นยาว ราคาอยู่เหนือ EMA ทั้งหมด ไม่แตะ EMA200 ไม่ทะลุ EMA100
    → direction CALL แต่ tier NONE (ยังไม่เข้าเงื่อนไข)"""
    df = flat_then_rise()
    res = score_setup(df, timeframe="M5")
    assert res.direction == "CALL"
    assert res.bias == "BULLISH_TREND"
    assert res.importance == 0
    assert res.tier == "NONE"
    assert res.entry_trigger is False
    assert res.conditions_total == 11
    assert res.ema200_price is not None


def test_score_setup_downtrend_direction_put():
    """กรณีกลับข้าง: แบนราบแล้วดิ่งลง → direction PUT (EMA 50<100<200)"""
    closes = [2520.0] * 220
    step = (2520.0 - 2400.0) / 90
    closes += [2520.0 - step * (i + 1) for i in range(90)]  # ดิ่งลงต่อเนื่อง
    df = mk_df(closes)
    res = score_setup(df, timeframe="M5")
    assert res.direction == "PUT"
    assert res.bias == "BEARISH_TREND"


def test_score_setup_ema200_touch_fires_importance1():
    """แบนราบ 2400 (EMA200 = 2400 พอดี) แท่งสุดท้ายไล่จากเหนือเส้นลงไปแตะเส้น
    → importance 1 = FIRE ทันที แม้ผ่าน checklist แค่บางข้อ"""
    closes = [2400.0] * 220
    opens = [2400.0] * 220
    highs = [2400.5] * 220
    lows = [2399.5] * 220
    # แท่งสุดท้าย: เปิด 2400.3 → ปิด 2400.0 (แตะเส้นพอดี, wick ลงต่ำกว่าเส้น)
    opens[-1] = 2400.3
    highs[-1] = 2400.4
    lows[-1] = 2399.6
    closes[-1] = 2400.0
    df = mk_df(closes, highs=highs, lows=lows, opens=opens)
    res = score_setup(df, timeframe="M5")
    assert res.touched_ema200 is True
    assert res.importance == 1
    assert res.tier == "FIRE"
    assert res.entry_trigger is True
    assert res.direction == "CALL"          # ปิดบนเส้น (>=) → CALL
    assert res.touch_case != ""
    assert res.conditions_total == 11
    assert len(res.conditions_log) == 11
    # score = จำนวนข้อที่ผ่าน
    passed = sum(1 for c in res.conditions_log.values() if c["pass"])
    assert res.conditions_passed == passed
    assert res.score == float(passed)


def test_score_setup_pullback_to_ema100_is_importance2():
    """ไต่ขึ้นแล้วย่อลงมาอยู่ระหว่าง EMA200 กับ EMA100 (ยังไม่แตะ EMA200)
    → importance 2; tier WATCH หรือ FIRE ตามจำนวนข้อที่ผ่าน (เกณฑ์ 7/11)"""
    df = flat_then_rise()
    e100 = float(ema(df["close"], 100).iloc[-1])
    e200 = float(ema(df["close"], 200).iloc[-1])
    mid = (e100 + e200) / 2.0
    # แท่งสุดท้ายย่อลงมาอยู่กึ่งกลางระหว่าง EMA200-EMA100
    df.iloc[-1, df.columns.get_loc("close")] = mid
    df.iloc[-1, df.columns.get_loc("high")] = mid + 0.5
    df.iloc[-1, df.columns.get_loc("low")] = mid - 0.5
    res = score_setup(df, timeframe="M5")
    assert res.crossed_ema100 is True
    assert res.touched_ema200 is False
    assert res.importance == 2
    assert res.tier in ("WATCH", "FIRE")
    # พฤติกรรม two-tier: FIRE ⟺ entry_trigger
    assert res.entry_trigger == (res.tier == "FIRE")
    if res.tier == "WATCH":
        assert res.conditions_passed < 7


def test_score_setup_score_equals_passed_count():
    df = flat_then_rise()
    res = score_setup(df, timeframe="M5")
    passed = sum(1 for c in res.conditions_log.values() if c["pass"])
    assert res.conditions_passed == passed
    assert res.score == float(passed)
    # ทุกข้อใน log มีโครงสร้าง {"pass", "note"} เหมือนเดิม
    for c in res.conditions_log.values():
        assert "pass" in c and "note" in c


def test_score_setup_never_crashes_on_noisy_data():
    """ราคาสุ่ม (EMA ไม่เรียง/สลับ) → ต้อง return ผลลัพธ์ที่ valid เสมอ ไม่พัง"""
    rng = np.random.default_rng(42)
    closes = list(2400.0 + rng.normal(0, 8.0, 300).cumsum() * 0.02)
    df = mk_df(closes)
    res = score_setup(df, timeframe="M5")
    assert res.max_score == 11
    assert res.tier in ("NONE", "WATCH", "FIRE")