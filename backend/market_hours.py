"""
market_hours.py — เลือก Symbol ให้ระบบรันได้ตลอด (แม้ตลาดทองจริงปิดเสาร์-อาทิตย์)
=====================================================================================
ราคาทองจริง (frxXAUUSD) เป็นสินค้า Forex/Commodity → ตลาดปิดวันเสาร์-อาทิตย์ (UTC)
และช่วงปิดรายวัน ~21:00-22:00 UTC ทำให้ Deriv ไม่ส่ง tick สดในช่วงนั้น

วิธีรับมือ: สลับไปใช้ Synthetic Index ของ Deriv ที่เทรดได้ 24/7 (ค่า default: R_100
Volatility 100 Index) เพื่อให้ pipeline ยังทำงาน/เก็บ log/ยิง Telegram ตลอดเวลา
เมื่อตลาดเปิดอีกครั้ง ระบบจะกลับมาใช้ symbol หลักเองอัตโนมัติ (เพราะเลือกใหม่ทุกครั้ง)

ตั้งค่าใน .env:
    DERIV_SYMBOL=frxXAUUSD           # ตัวหลัก ราคาทองจริง
    DERIV_SYMBOL_BACKUP=R_100        # ตัวสำรอง ตลาดเปิด 24/7
    SYMBOL_AUTO_FALLBACK=true        # false = ปิดการสลับอัตโนมัติ
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

DEFAULT_SYMBOL = "frxXAUUSD"
DEFAULT_BACKUP = "R_100"


def is_forex_like(symbol: str) -> bool:
    """สัญลักษณ์ forex/commodity ของ Deriv ขึ้นต้นด้วย frx (เช่น frxXAUUSD, frxEURUSD)"""
    return (symbol or "").startswith("frx")


def market_open_now(now: datetime | None = None) -> bool:
    """ตลาด Forex เปิดหรือไม่ (อิงเวลา UTC)

    ตารางจริง (DST โดยประมาณ — ใช้กรอบคงที่เพื่อความเรียบง่าย):
      เปิด: อาทิตย์ 22:00 UTC → ศุกร์ 21:00 UTC
      ปิด: ศุกร์ 21:00 → อาทิตย์ 22:00 (สุดสัปดาห์) + ปิดรายวัน 21:00-22:00 UTC
    (เดิมปล่อยผ่านศุกร์ 22:00-23:59 ทั้งที่ตลาดปิดแล้ว)
    """
    now = now or datetime.now(timezone.utc)
    wd = now.weekday()  # 0=จันทร์ ... 4=ศุกร์, 5=เสาร์, 6=อาทิตย์
    minutes = now.hour * 60 + now.minute
    if wd == 4 and minutes >= 21 * 60:  # ศุกร์ ≥ 21:00 → ปิดแล้ว
        return False
    if wd >= 5:  # เสาร์/อาทิตย์ (จนถึงอาทิตย์ 22:00)
        return wd == 6 and minutes >= 22 * 60  # อาทิตย์ ≥ 22:00 = เปิดสัปดาห์ใหม่
    if wd == 0 and minutes < 22 * 60:  # จันทร์ < 22:00 → ยังอยู่ในช่วงเปิดตลาดอาทิตย์/ก่อนเปิด
        return False
    if 21 * 60 <= minutes < 22 * 60:  # ปิดรายวัน 21:00-22:00 UTC
        return False
    return True


def choose_symbol(now: datetime | None = None) -> str:
    """คืน symbol ที่ควรใช้ตอนนี้: ถ้า symbol หลักเป็น forex และตลาดปิด → ใช้ตัวสำรอง"""
    auto = os.getenv("SYMBOL_AUTO_FALLBACK", "true").strip().lower() != "false"
    primary = os.getenv("DERIV_SYMBOL", DEFAULT_SYMBOL)
    backup = os.getenv("DERIV_SYMBOL_BACKUP", DEFAULT_BACKUP)
    if auto and backup and is_forex_like(primary) and not market_open_now(now):
        return backup
    return primary


def market_open_cooldown(now: datetime | None = None, cooldown_min: int = 15) -> bool:
    """True ถ้าอยู่ในช่วง cooldown หลังตลาดเปิดสัปดาห์ (อาทิตย์ 22:00 UTC + cooldown_min)

    ตลาด forex เปิดจริง = อาทิตย์ 22:00 UTC (ไม่ใช่จันทร์ 00:00 แบบเดิม) —
    ช่วงเปิดใหม่ spread กว้าง + whipsaw รุนแรง จึงบล็อกสัญญาณช่วงสั้น ๆ หลังเปิด
    (ครอบคลุมช่วงข้ามวัน: อาทิตย์ 22:00-23:59 + จันทร์ 00:00-เช้าถ้า cooldown ยาว)
    """
    now = now or datetime.now(timezone.utc)
    wd = now.weekday()
    minutes = now.hour * 60 + now.minute
    if wd == 6 and minutes >= 22 * 60:  # อาทิตย์หลังเปิด 22:00
        minutes_since_open = minutes - 22 * 60
    elif wd == 0:  # จันทร์: นับต่อจากเปิด 22:00 ของอาทิตย์
        minutes_since_open = 2 * 60 + minutes  # 22:00 อาทิตย์ → 00:00 จันทร์ = 120 นาที
    else:
        return False
    return minutes_since_open < cooldown_min


def symbol_label(symbol: str) -> str:
    """ชื่อที่ใช้ใน Telegram message — XAUUSD สำหรับทองจริง, R_100 สำหรับตัวสำรอง"""
    if symbol == "frxXAUUSD":
        return "XAUUSD"
    return symbol


def get_session(now: datetime | None = None) -> str:
    """ระบุ session ปัจจุบัน (UTC) — Asia/London/NY/Night"""
    now = now or datetime.now(timezone.utc)
    h = now.hour
    if h < 7:
        return "Asia"
    elif h < 13:
        return "London"
    elif h < 18:
        return "NY"
    else:
        return "Night"


def should_block_call(now: datetime | None = None) -> bool:
    """True ถ้าควรบล็อกสัญญาณ CALL ใน session นี้
      ข้อมูลจาก 482 trades:
    CALL Night (18-24 UTC): 34.1% WR (41 trades) → บล็อก
    CALL Asia: 43.8%, London: 46.2%, NY: 48.8% → ยังพอได้
    """
    return get_session(now) == "Night"


def should_block_put(now: datetime | None = None) -> bool:
    """True ถ้าควรบล็อกสัญญาณ PUT ใน session นี้
    PUT ทุก session ยัง OK (45-63%) — ไม่บล็อก แต่ London = Golden Zone
    """
    return False
