"""tests/test_setup_feed_h1.py — V2 gates: โครงสร้างข้อมูล H1 + แก้ repaint (แผน C2)

ตาม docs/plan_setup_v2_gates.md ข้อ 2.1 / 2.3 — deterministic ไม่ดึงเน็ต ไม่แตะ DB
(สร้าง engine ผ่าน __new__ เพื่อข้าม __init__ ที่ seed ผ่าน network)
"""

import pandas as pd

from backend.setup_feed import SetupFeedEngine


def make_engine(buffer: pd.DataFrame) -> SetupFeedEngine:
    eng = SetupFeedEngine.__new__(SetupFeedEngine)
    eng.symbol = "frxXAUUSD"
    eng.buffer = buffer
    eng._h1_closes = pd.Series(dtype=float)
    eng._h1_trend = None
    return eng


def m1_df(start: str, n: int, base: float = 2400.0, volume: float = 1.0) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [base] * n,
            "high": [base + 0.5] * n,
            "low": [base - 0.5] * n,
            "close": [base] * n,
            "volume": [volume] * n,
        },
        index=idx,
    )


# ── _update_h1_trend ─────────────────────────────────────────────────────────
def test_h1_trend_up_when_close_above_ema200():
    eng = make_engine(m1_df("2026-11-20 09:00", 1))
    hours = pd.date_range("2026-09-01 00:00", periods=400, freq="1h", tz="UTC")
    eng._h1_closes = pd.Series([2400.0 + i * 0.5 for i in range(400)], index=hours)
    eng._update_h1_trend()
    assert eng._h1_trend == "UP"


def test_h1_trend_down_when_close_below_ema200():
    eng = make_engine(m1_df("2026-11-20 09:00", 1))
    hours = pd.date_range("2026-09-01 00:00", periods=400, freq="1h", tz="UTC")
    eng._h1_closes = pd.Series([2600.0 - i * 0.5 for i in range(400)], index=hours)
    eng._update_h1_trend()
    assert eng._h1_trend == "DOWN"


def test_h1_trend_none_fail_closed_when_history_short():
    """ข้อมูล H1 < 300 ชม. → None → เกต h1 จะไม่ผ่าน (fail-closed)"""
    eng = make_engine(m1_df("2026-11-20 09:00", 1))
    hours = pd.date_range("2026-11-01 00:00", periods=299, freq="1h", tz="UTC")
    eng._h1_closes = pd.Series([2400.0] * 299, index=hours)
    eng._update_h1_trend()
    assert eng._h1_trend is None


# ── _update_h1_from_buffer ──────────────────────────────────────────────────
def test_update_h1_uses_closed_hours_only_no_lookahead():
    """ชั่วโมง 09:00 ปิดครบ 60 แท่ง + แท่ง 10:00 กำลังก่อตัว →
    H1 series ต้องมีชั่วโมง 09:00 (close = แท่ง 09:59) และ "ไม่มี" 10:00"""
    eng = make_engine(m1_df("2026-11-20 09:00", 61))
    eng.buffer.iloc[-1, eng.buffer.columns.get_loc("close")] = 9999.0  # แท่งก่อตัว
    eng._update_h1_from_buffer()
    assert list(eng._h1_closes.index) == [pd.Timestamp("2026-11-20 09:00", tz="UTC")]
    assert float(eng._h1_closes.iloc[-1]) == 2400.0  # ไม่หยิบ 9999 ของแท่งก่อตัว


def test_update_h1_skips_thin_hours():
    """ชั่วโมงที่มีแท่ง M1 ปิดแล้ว < 30 แท่ง (ขาดข้อมูลกลางคัน) → ไม่นับ"""
    df = m1_df("2026-11-20 09:00", 20)  # 20 แท่งในชั่วโมงเดียว ไม่มีแท่งก่อตัง
    df.loc[df.index[-1], "close"] = 2400.0
    eng = make_engine(df)
    eng.buffer = df.iloc[:-1].copy()  # จำลอง: ทุกแท่งถือเป็นปิดแล้วหมด
    eng._update_h1_from_buffer()
    assert eng._h1_closes.empty


# ── _resample(closed_only=True) — แก้ repaint แผน C2 ─────────────────────────
def test_resample_closed_only_drops_partial_m5_tail():
    """แท่ง M5 ท้ายสุดยังไม่ครบ 5 นาที → ตัดออก (ประเมินเฉพาะแท่งปิด)"""
    eng = make_engine(m1_df("2026-11-20 10:00", 8))  # 10:00-10:07 (แท่ง 10:07 ก่อตัว)
    out = eng._resample(5, closed_only=True)
    assert list(out.index) == [pd.Timestamp("2026-11-20 10:00", tz="UTC")]


def test_resample_closed_only_keeps_full_m5_tail():
    """แท่ง M5 ครบ 5 นาทีแล้วทุกถัง → คงไว้ (เทียบ: แบบเดิมออก 2 ถัง)"""
    eng = make_engine(m1_df("2026-11-20 10:00", 11))  # 10:00-10:10 (แท่ง 10:10 ก่อตัง)
    out_closed = eng._resample(5, closed_only=True)
    out_legacy = eng._resample(5)
    assert len(out_closed.index) == 2  # 10:00 + 10:05 ครบถังทั้งคู่
    assert len(out_legacy.index) == 3  # legacy รวมถังก่อตัง → 3


def test_resample_legacy_default_unchanged():
    """closed_only=False (default) → พฤติกรรมเดิม: รวมแท่งกำลังก่อตัว"""
    eng = make_engine(m1_df("2026-11-20 10:00", 8))
    out = eng._resample(5)
    assert len(out.index) == 2  # 10:00 + 10:05 (บาง) เหมือนก่อนแก้
