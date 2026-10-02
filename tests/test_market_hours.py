"""Characterization tests — backend/market_hours.py

ล็อกพฤติกรรมเดิมของตรรกะเวลาตลาด/symbol fallback ทั้งหมด
(ทุกฟังก์ชันเป็น pure function รับ `now` เข้ามาได้ → ทดสอบได้ตรง ๆ ไม่แตะเน็ต/DB)
"""
from datetime import datetime, timezone

from backend.market_hours import (
    choose_symbol,
    get_session,
    is_forex_like,
    market_open_cooldown,
    market_open_now,
    should_block_call,
    should_block_put,
    symbol_label,
)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# ── is_forex_like ────────────────────────────────────────────────────────────
def test_is_forex_like():
    assert is_forex_like("frxXAUUSD") is True
    assert is_forex_like("frxEURUSD") is True
    assert is_forex_like("R_100") is False
    assert is_forex_like("") is False
    assert is_forex_like(None) is False  # ไม่พังกับ None


# ── market_open_now (เกณฑ์เดิม: เสาร์/อาทิตย์ + ชั่วโมง 21 UTC = ปิด) ──────────
def test_market_open_weekday():
    # พุธ 10:00 UTC → เปิด
    assert market_open_now(utc(2026, 8, 12, 10, 0)) is True
    # พุธ 20:59 UTC → เปิด (ยังไม่ถึงชั่วโมง 21)
    assert market_open_now(utc(2026, 8, 12, 20, 59)) is True
    # พุธ 21:00 UTC → ปิด (ปิดรายวัน)
    assert market_open_now(utc(2026, 8, 12, 21, 0)) is False
    # พุธ 21:59 UTC → ปิด
    assert market_open_now(utc(2026, 8, 12, 21, 59)) is False
    # พฤหัส 22:00 UTC → เปิด
    assert market_open_now(utc(2026, 8, 13, 22, 0)) is True


def test_market_open_weekend():
    # เสาร์ (weekday=5) ปิดทุกชั่วโมง
    assert market_open_now(utc(2026, 8, 15, 10, 0)) is False
    # อาทิตย์ (weekday=6) ปิดทุกชั่วโมง
    assert market_open_now(utc(2026, 8, 16, 10, 0)) is False


# ── choose_symbol (fallback ตาม env) ─────────────────────────────────────────
def test_choose_symbol_fallback_when_closed(monkeypatch):
    monkeypatch.setenv("SYMBOL_AUTO_FALLBACK", "true")
    monkeypatch.setenv("DERIV_SYMBOL", "frxXAUUSD")
    monkeypatch.setenv("DERIV_SYMBOL_BACKUP", "R_100")
    # เสาร์ = ตลาดจริงปิด → ใช้ตัวสำรอง
    assert choose_symbol(utc(2026, 8, 15, 10, 0)) == "R_100"
    # พุธ 10:00 = ตลาดเปิด → ใช้ตัวหลัก
    assert choose_symbol(utc(2026, 8, 12, 10, 0)) == "frxXAUUSD"
    # พุธ 21:30 = ปิดรายวัน → ตัวสำรอง
    assert choose_symbol(utc(2026, 8, 12, 21, 30)) == "R_100"


def test_choose_symbol_auto_false(monkeypatch):
    monkeypatch.setenv("SYMBOL_AUTO_FALLBACK", "false")
    monkeypatch.setenv("DERIV_SYMBOL", "frxXAUUSD")
    monkeypatch.setenv("DERIV_SYMBOL_BACKUP", "R_100")
    # ปิด auto → คงใช้ตัวหลักแม้ตลาดปิด
    assert choose_symbol(utc(2026, 8, 15, 10, 0)) == "frxXAUUSD"


def test_choose_symbol_primary_not_forex(monkeypatch):
    monkeypatch.setenv("SYMBOL_AUTO_FALLBACK", "true")
    monkeypatch.setenv("DERIV_SYMBOL", "R_100")
    monkeypatch.setenv("DERIV_SYMBOL_BACKUP", "1HZ100V")
    # ตัวหลักไม่ใช่ forex → ไม่ fallback (คงใช้ R_100 แม้เสาร์)
    assert choose_symbol(utc(2026, 8, 15, 10, 0)) == "R_100"


# ── market_open_cooldown (กันสัญญาณถล่มตอนตลาดเปิดสัปดาห์) ────────────────────
def test_market_open_cooldown_monday_early():
    # จันทร์ 00:10 UTC → 10 นาที < 15 → cooldown
    assert market_open_cooldown(utc(2026, 8, 17, 0, 10)) is True
    # จันทร์ 00:00 พอดี → cooldown
    assert market_open_cooldown(utc(2026, 8, 17, 0, 0)) is True
    # จันทร์ 00:15 → ยัง cooldown (15 < 15 = False → ไม่ cooldown)
    assert market_open_cooldown(utc(2026, 8, 17, 0, 15)) is False
    # จันทร์ 00:20 → หมด cooldown
    assert market_open_cooldown(utc(2026, 8, 17, 0, 20)) is False


def test_market_open_cooldown_other_days():
    assert market_open_cooldown(utc(2026, 8, 18, 0, 5)) is False  # อังคาร
    assert market_open_cooldown(utc(2026, 8, 15, 0, 5)) is False  # เสาร์


# ── symbol_label ─────────────────────────────────────────────────────────────
def test_symbol_label():
    assert symbol_label("frxXAUUSD") == "XAUUSD"
    assert symbol_label("R_100") == "R_100"
    assert symbol_label("frxXAGUSD") == "frxXAGUSD"


# ── get_session (เขตเวลาเซสชันแบบเดิม) ───────────────────────────────────────
def test_get_session_boundaries():
    assert get_session(utc(2026, 8, 12, 0, 0)) == "Asia"
    assert get_session(utc(2026, 8, 12, 6, 59)) == "Asia"
    assert get_session(utc(2026, 8, 12, 7, 0)) == "London"
    assert get_session(utc(2026, 8, 12, 12, 59)) == "London"
    assert get_session(utc(2026, 8, 12, 13, 0)) == "NY"
    assert get_session(utc(2026, 8, 12, 17, 59)) == "NY"
    assert get_session(utc(2026, 8, 12, 18, 0)) == "Night"
    assert get_session(utc(2026, 8, 12, 23, 59)) == "Night"


# ── session blocks (จากสถิติ 482 trades เดิม) ────────────────────────────────
def test_should_block_call_night_only():
    assert should_block_call(utc(2026, 8, 12, 20, 0)) is True   # Night
    assert should_block_call(utc(2026, 8, 12, 23, 0)) is True   # Night
    assert should_block_call(utc(2026, 8, 12, 15, 0)) is False  # NY
    assert should_block_call(utc(2026, 8, 12, 9, 0)) is False   # London


def test_should_block_put_never():
    for h in (2, 9, 15, 20):
        assert should_block_put(utc(2026, 8, 12, h, 0)) is False