"""test_auto_retrain_price_data.py — กันแถวขยะ CSV ทำ auto_retrain crash

บั๊กจริงบน VPS (10 ต.ค. 2026): deriv_R_100_60s.csv มีแถวขยะ "0" หนึ่งแถว
→ pd.read_csv(parse_dates=["datetime"]) ได้ index เป็น object
→ `df.index.tz` crash AttributeError → auto_retrain ตายทุกรอบทุก 6 ชม.
→ โมเดลไม่ถูกเทรนใหม่ตั้งแต่ 2 ส.ค. — เทสต์นี้การันตีว่าแถวเสียถูกข้ามเงียบ ๆ
"""

from __future__ import annotations

import pandas as pd

import backend.ml_forecaster.auto_retrain as ar


def _write_csv(path, body: str) -> None:
    path.write_text("datetime,open,high,low,close,volume\n" + body, encoding="utf-8")


def test_garbage_row_does_not_crash(tmp_path, monkeypatch):
    """แถวขยะ "0" + วันที่เพี้ยน ต้องถูกข้าม ไม่ crash และได้ index tz-aware UTC"""
    _write_csv(
        tmp_path / "deriv_frxXAUUSD_60s.csv",
        (
            "2026-10-01 00:00:00+00:00,4000.0,4001.0,3999.0,4000.5,0\n"
            "0\n"  # แถวขยะแบบเดียวกับที่เจอบน VPS
            "bad-date,x,x,x,x,0\n"  # วันที่เพี้ยน + ตัวเลขเพี้ยน
            "2026-10-01 00:05:00+00:00,4000.5,4002.0,4000.0,4001.0,0\n"
        ),
    )
    monkeypatch.setattr(
        ar,
        "_load_prices_from_db",
        lambda *a, **k: pd.DataFrame(columns=["open", "high", "low", "close", "volume"]),
    )
    df = ar._load_price_data(data_dir=tmp_path)
    # 2 แท่งจริง (00:00 + 00:05) — หลัง resample M5 ยังแยกกัน
    assert len(df) == 2
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.tz is not None


def test_empty_and_missing_files_return_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ar,
        "_load_prices_from_db",
        lambda *a, **k: pd.DataFrame(columns=["open", "high", "low", "close", "volume"]),
    )
    df = ar._load_price_data(data_dir=tmp_path)
    assert df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_numeric_garbage_filtered(tmp_path, monkeypatch):
    """ตัวเลขเพี้ยน (text ในคอลัมน์ OHLC) ต้องถูกกรองออก"""
    _write_csv(
        tmp_path / "deriv_R_100_60s.csv",
        (
            "2026-10-01 00:00:00+00:00,not-num,4001,3999,4000,0\n"
            "2026-10-01 00:05:00+00:00,500,501,499,500.5,0\n"
        ),
    )
    monkeypatch.setattr(
        ar,
        "_load_prices_from_db",
        lambda *a, **k: pd.DataFrame(columns=["open", "high", "low", "close", "volume"]),
    )
    df = ar._load_price_data(data_dir=tmp_path)
    assert len(df) == 1
    assert float(df["close"].iloc[0]) == 500.5


def test_load_prices_from_db(temp_db):
    """_load_prices_from_db ดึงจากตาราง prices จริง (patch DB ชั่วคราวตาม conftest)"""
    import backend.db as db

    db.insert_price("2026-10-30T10:00:00+00:00", 4000.0, 4001.0, 3999.0, 4000.5, symbol="frxXAUUSD")
    db.insert_price("2026-10-30T10:01:00+00:00", 4000.5, 4002.0, 4000.0, 4001.0, symbol="frxXAUUSD")
    df = ar._load_prices_from_db()
    assert len(df) == 2
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.tz is not None
    # query ORDER BY ts DESC → แถวใหม่สุด (10:01) อยู่แถวแรก
    assert float(df["close"].iloc[0]) == 4001.0
    assert float(df["close"].iloc[-1]) == 4000.5
    # volume เติม 0.0 ให้ครบ schema เดียวกับ CSV
    assert float(df["volume"].iloc[-1]) == 0.0
