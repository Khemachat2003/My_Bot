"""
json_safe.py — ตัวช่วยกลางสำหรับแปลงค่าที่มาจาก numpy/pandas/datetime/Decimal/Enum
ให้เป็น native Python type ก่อนส่งเข้า json.dumps() หรือ FastAPI JSONResponse

ทำไมต้องมีไฟล์นี้:
numpy.bool_ / numpy.int64 / numpy.float32 ฯลฯ "หน้าตา" เหมือนชนิดข้อมูล python ปกติ
และหลายค่าก็ใช้ในเงื่อนไข if/and/or ได้ตามปกติ แต่ json.dumps() ของมาตรฐาน
Python ไม่รู้จักชนิดพวกนี้โดยตรง (ยกเว้น numpy.float64 ที่บังเอิญสืบทอดจาก
python float เลยผ่านได้ — แต่ numpy.bool_ และ numpy.int64 ไม่ได้สืบทอดจาก
bool/int เลย error จะโผล่ตอน serialize เท่านั้น ไม่ใช่ตอนคำนวณ ทำให้ดีบักยาก)

ใช้งาน:
    from backend.json_safe import to_json_safe, safe_json_dumps

    json.dumps(to_json_safe(some_dict))
    # หรือ
    safe_json_dumps(some_dict)
"""
from __future__ import annotations

import json
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from enum import Enum
from typing import Any

import numpy as np

try:
    import pandas as pd
except ImportError:  # pandas เป็น optional สำหรับ utility ตัวนี้
    pd = None  # type: ignore


def to_json_safe(value: Any) -> Any:
    """แปลง value (รวมถึง nested dict/list/tuple/set) ให้เป็นชนิดที่
    json.dumps มาตรฐานจัดการได้เสมอ ไม่ throw

    ลำดับการเช็ค: numpy scalar/array ก่อน (ครอบคลุม bool_/int64/float64/ndarray)
    → pandas Timestamp/NaT → datetime/date/time → Decimal → Enum
    → dict/list/tuple/set (recursive) → ปล่อยผ่านถ้าเป็น str/int/float/bool/None อยู่แล้ว
    """
    # numpy bool ก่อน int/float เพราะ np.bool_ อาจถูกเข้าใจผิดว่าเป็น int ได้ในบาง path
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        f = float(value)
        return None if np.isnan(f) or np.isinf(f) else f
    if isinstance(value, np.ndarray):
        return [to_json_safe(v) for v in value.tolist()]

    if pd is not None:
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if value is pd.NaT:
            return None
        if isinstance(value, pd.Series):
            return {to_json_safe(k): to_json_safe(v) for k, v in value.to_dict().items()}
        if isinstance(value, pd.DataFrame):
            return [to_json_safe(row) for row in value.to_dict(orient="records")]

    if isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return to_json_safe(value.value)

    if isinstance(value, dict):
        return {str(to_json_safe(k)): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_safe(v) for v in value]

    # float("nan") / float("inf") ธรรมดาก็ทำให้ json.dumps พังได้เหมือนกัน (ค่า default
    # allow_nan=True จริง ๆ ปล่อยผ่านได้ แต่ผลลัพธ์ไม่ใช่ JSON มาตรฐาน — กันไว้ให้ปลอดภัยสุด)
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None

    return value


def safe_json_dumps(value: Any, **kwargs) -> str:
    """json.dumps ที่ผ่าน to_json_safe() ให้ก่อนเสมอ — ใช้แทน json.dumps ตรงๆ
    ได้ทุกที่ (sqlite storage, Telegram payload, dashboard API ฯลฯ)
    """
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(to_json_safe(value), **kwargs)
