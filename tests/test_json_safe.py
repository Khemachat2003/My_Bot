"""Characterization tests — backend/json_safe.py

ล็อกพฤติกรรมตัวแปลงค่า numpy/pandas/datetime → ชนิดที่ json.dumps ได้
(ใช้จริงทั้ง sqlite storage / Telegram payload / dashboard API)
"""
import json
from datetime import datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from backend.json_safe import safe_json_dumps, to_json_safe


def test_numpy_scalars():
    assert to_json_safe(np.bool_(True)) is True
    assert to_json_safe(np.int64(42)) == 42
    assert isinstance(to_json_safe(np.int64(42)), int)
    assert to_json_safe(np.float32(1.5)) == 1.5
    assert isinstance(to_json_safe(np.float32(1.5)), float)


def test_numpy_nan_inf_become_none():
    assert to_json_safe(np.float64(float("nan"))) is None
    assert to_json_safe(np.float64(float("inf"))) is None
    assert to_json_safe(np.float64(float("-inf"))) is None


def test_plain_float_nan_inf_become_none():
    assert to_json_safe(float("nan")) is None
    assert to_json_safe(float("inf")) is None


def test_numpy_array_and_series():
    assert to_json_safe(np.array([1, 2, 3])) == [1, 2, 3]
    assert to_json_safe(pd.Series({"a": 1})) == {"a": 1}
    rows = to_json_safe(pd.DataFrame([{"x": np.int64(1)}]))
    assert rows == [{"x": 1}]


def test_datetime_and_timestamp():
    dt = datetime(2026, 8, 14, 10, 30, 0)
    assert to_json_safe(dt) == "2026-08-14T10:30:00"
    ts = pd.Timestamp("2026-08-14 10:30:00")
    assert to_json_safe(ts) == ts.isoformat()
    assert to_json_safe(pd.NaT) is None


def test_decimal_and_nested():
    data = {
        "dec": Decimal("1.25"),
        "nested": {"arr": (np.int64(1), np.bool_(False)), "set": {1, 2}},
    }
    out = to_json_safe(data)
    assert out["dec"] == 1.25
    assert out["nested"]["arr"] == [1, False]
    assert sorted(out["nested"]["set"]) == [1, 2]


def test_safe_json_dumps_never_throws():
    payload = {"nan": float("nan"), "ts": pd.Timestamp("2026-08-14"),
               "npbool": np.bool_(True), "ไทย": "ทดสอบ"}
    text = safe_json_dumps(payload)
    # ต้อง parse กลับได้ และไม่มี NaN ตกค้าง (มาตรฐาน JSON)
    parsed = json.loads(text)
    assert parsed["nan"] is None
    assert parsed["npbool"] is True
    assert parsed["ไทย"] == "ทดสอบ"