"""Characterization tests — mt5_executor.py (ฝั่ง pure functions เท่านั้น)

ครอบพฤติกรรมการคำนวณ SL/TP (fractal + ATR), parse เวลาสัญญาณ, คิด volume,
และ symbol mapping — ไม่แตะ MT5 terminal, ไม่ส่งออเดอร์จริงทุกกรณี
"""
import datetime as dt

import pandas as pd
import pytest

import mt5_executor as ex


@pytest.fixture(autouse=True)
def force_mt5_none(monkeypatch):
    """ล็อกเส้นทาง mt5=None (ไม่มี terminal) — ทำให้คำนวณ deterministic"""
    monkeypatch.setattr(ex, "mt5", None)


def flat_df(n=30, high=101.0, low=100.0, close=100.5):
    idx = pd.date_range("2026-08-14 10:00", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"open": [close] * n, "high": [high] * n,
                         "low": [low] * n, "close": [close] * n}, index=idx)


# ── parse_sig_time ───────────────────────────────────────────────────────────
def test_parse_sig_time_with_z():
    t = ex.parse_sig_time("2026-08-14T10:00:00Z")
    assert t.utcoffset() == dt.timedelta(0)
    assert (t.year, t.month, t.day, t.hour) == (2026, 8, 14, 10)


def test_parse_sig_time_naive_assumed_utc():
    t = ex.parse_sig_time("2026-08-14T10:00:00")
    assert t.tzinfo is not None
    assert t.utcoffset() == dt.timedelta(0)


def test_parse_sig_time_with_offset_kept():
    t = ex.parse_sig_time("2026-08-14T17:00:00+07:00")
    assert t.utcoffset() == dt.timedelta(hours=7)


# ── _atr ─────────────────────────────────────────────────────────────────────
def test_atr_constant_range_is_exact():
    """แท่งทุกแท่ง high-low = 1 และ close ทึบ → TR = 1 ทุกแท่ง → ATR = 1.0"""
    df = flat_df(n=30)
    assert ex._atr(df) == pytest.approx(1.0)


def test_atr_short_series_min_periods():
    """ต่ำกว่า period=14 → ewm ยังไม่ออกค่า (NaN) → ATR ต้องเป็น NaN ไม่พัง"""
    df = flat_df(n=10)
    val = ex._atr(df)
    import math
    assert math.isnan(val)


# ── compute_sl_tp ────────────────────────────────────────────────────────────
def test_compute_sl_tp_buy_uses_fractal_low_with_buffer():
    """flat series → ทุกแท่งเป็น fractal low (low=100) ใต้ entry=100.5
    → SL = fractal_low - buffer*ATR = 100 - 0.25 = 99.75
    → TP = entry + rr*(entry-SL) = 100.5 + 2.0*0.75 = 102.0"""
    df = flat_df(n=40)
    sl, tp = ex.compute_sl_tp(df, "BUY", entry=100.5, rr=2.0,
                              atr_mult=1.5, buffer_mult=0.25)
    assert sl == pytest.approx(99.75)
    assert tp == pytest.approx(102.0)
    assert sl < 100.5 < tp


def test_compute_sl_tp_sell_uses_fractal_high_with_buffer():
    """ฝั่ง SELL: SL = fractal_high + buffer = 101.25
    → TP = entry - rr*(SL-entry) = 100.5 - 2.0*0.75 = 99.0"""
    df = flat_df(n=40)
    sl, tp = ex.compute_sl_tp(df, "SELL", entry=100.5, rr=2.0,
                              atr_mult=1.5, buffer_mult=0.25)
    assert sl == pytest.approx(101.25)
    assert tp == pytest.approx(99.0)
    assert tp < 100.5 < sl


def test_compute_sl_tp_rr_ratio_consistent():
    """ความสัมพันธ์หลักของ R:R ต้องคงอยู่ทุกกรณี: TP dist = rr × SL dist"""
    df = flat_df(n=40)
    for rr in (1.5, 2.0, 3.0):
        sl, tp = ex.compute_sl_tp(df, "BUY", entry=100.5, rr=rr,
                                  atr_mult=1.5, buffer_mult=0.25)
        assert (tp - 100.5) == pytest.approx(rr * (100.5 - sl))


def test_compute_sl_tp_sl_capped_minimum_half_atr():
    """fractal low อยู่ใกล้ entry เกิน → ต้อง cap ที่ entry - 0.5*ATR (ฝั่ง BUY)

    คำนวณจาก df นี้: TR = max(101-100.45, |101-100.5|, |100.45-100.5|) = 0.55 → ATR = 0.55
      fractal_sl = 100.45 - 0.25*0.55 = 100.3125
      cap        = 100.5 - 0.5*0.55  = 100.225  ← ใช้ค่านี้ (min)
      tp         = 100.5 + 2.0*(100.5-100.225) = 101.05
    """
    df = flat_df(n=40, high=101.0, low=100.45, close=100.5)
    sl, tp = ex.compute_sl_tp(df, "BUY", entry=100.5, rr=2.0,
                              atr_mult=1.5, buffer_mult=0.25)
    assert sl == pytest.approx(100.225)   # capped
    assert tp == pytest.approx(101.05)


def test_compute_sl_tp_short_df_returns_none():
    assert ex.compute_sl_tp(flat_df(n=29), "BUY", entry=100.5) is None


# ── calc_volume (เส้นทาง mt5=None: contract=100000, conv=1.0) ────────────────
def test_calc_volume_no_mt5():
    """risk 100 USD, dist 0.75 (100.5→99.75) → 100/(0.75*100000) ≈ 0.001333 lots"""
    vol = ex.calc_volume(entry=100.5, sl=99.75, risk_money=100.0, symbol="frxEURUSD")
    assert vol == pytest.approx(100.0 / (0.75 * 100000.0))


def test_calc_volume_zero_distance_returns_zero():
    assert ex.calc_volume(entry=100.5, sl=100.5, risk_money=100.0,
                          symbol="frxEURUSD") == 0.0


# ── FX_MAP (Deriv → MT5) ─────────────────────────────────────────────────────
def test_fx_map_major_pairs():
    assert ex.FX_MAP["frxEURUSD"] == "EURUSD"
    assert ex.FX_MAP["frxGBPUSD"] == "GBPUSD"
    assert ex.FX_MAP["frxUSDJPY"] == "USDJPY"
    assert ex.FX_MAP["frxAUDUSD"] == "AUDUSD"
    assert ex.FX_MAP["frxUSDCAD"] == "USDCAD"
    assert ex.FX_MAP["frxUSDCHF"] == "USDCHF"
    assert ex.FX_MAP["frxNZDUSD"] == "NZDUSD"


def test_place_order_dry_run_never_sends(monkeypatch):
    """dry-run ต้องไม่แตะ MT5 เลย และคืนรหัสลบ (−signal_id)"""
    called = {"mt5": False}
    ticket = ex.place_order("EURUSD", "BUY", entry=1.1, sl=1.09, tp=1.12,
                            volume=0.01, signal_id=42, dry=True)
    assert ticket == -42
    assert called["mt5"] is False