"""fixtures ร่วมของ characterization tests (Phase B — แยก backend/db.py + api.py)

หลักการ:
- ทุกเทสต์ต้องชี้ DB ไปยังไฟล์ชั่วคราว ห้ามแตะ data/bot.db จริง
- patch DB_PATH ของ "module ที่ get_conn อยู่จริง" — ก่อนแยก = backend.db (ไฟล์เดิม),
  หลังแยก = backend.db.connection เพราะ get_conn อ่านตัวแปร module ตัวเองตอน call-time
- ห้ามใช้ `with TestClient(...)` → ไม่รัน startup event (db.init_db() มี migration
  ที่ล้างข้อมูลค้าง — ดูหมายเหตุเดียวกันใน frontend/tests/visual/capture_fixtures.py)
"""

from __future__ import annotations

import pytest

import backend.db as db


def _conn_module():
    """module ที่ DB_PATH/get_conn อยู่จริง (รองรับทั้งโครงเดิมและโครงหลังแยก)"""
    try:
        from backend.db import connection as conn_mod  # หลังแยกเป็น package
    except ImportError:  # ก่อนแยก: DB_PATH/get_conn อยู่ใน backend/db.py เดิม
        conn_mod = db
    return conn_mod


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """ชี้ DB_PATH ของ backend.db ไปยัง tmp_path/bot.db + สร้างตารางครบ (คืน path)"""
    db_file = tmp_path / "bot.db"
    monkeypatch.setattr(_conn_module(), "DB_PATH", db_file)
    db.init_db()
    return db_file


@pytest.fixture()
def temp_setup_db(tmp_path, monkeypatch):
    """ชี้ DB_PATH ของ setup_db (ตาราง setup_scores) ไปยังไฟล์เดียวกับ temp_db"""
    from backend import setup_db

    db_file = tmp_path / "bot.db"
    monkeypatch.setattr(setup_db, "DB_PATH", db_file)
    setup_db.init_setup_db()
    return db_file


@pytest.fixture()
def api_client(temp_db, temp_setup_db, monkeypatch):
    """TestClient ของ backend.api.app แบบ auth ปิด + DB temp + ไม่รัน startup

    - auth ปิด = พฤติกรรม require_auth จริงเมื่อไม่ได้ตั้ง DASHBOARD_USER/PASS (dev localhost)
    - patch fetch_candles_history กันยิง Deriv network จริง
    - TestClient ไม่ใช้ `with` → ไม่ trigger startup event
    """
    from fastapi.testclient import TestClient

    import backend.data_feed.deriv_feed as deriv_feed
    from backend import api

    monkeypatch.setattr(api, "DASHBOARD_USER", None)
    monkeypatch.setattr(api, "DASHBOARD_PASS", None)
    monkeypatch.setattr(deriv_feed, "fetch_candles_history", lambda *a, **k: None)

    db.init_db()
    _clear_api_caches()
    # ไม่ใช้ `with TestClient(...)` → ไม่รัน startup (กัน migration แตะ DB จริง)
    return TestClient(api.app)


@pytest.fixture()
def auth_client(temp_db, temp_setup_db, monkeypatch):
    """TestClient แบบ auth เปิด (patch DASHBOARD_USER/PASS = ค่าทดสอบ)"""
    from fastapi.testclient import TestClient

    import backend.data_feed.deriv_feed as deriv_feed
    from backend import api

    monkeypatch.setattr(api, "DASHBOARD_USER", "user")
    monkeypatch.setattr(api, "DASHBOARD_PASS", "pass")
    monkeypatch.setattr(deriv_feed, "fetch_candles_history", lambda *a, **k: None)

    db.init_db()
    _clear_api_caches()
    return TestClient(api.app)


def _clear_api_caches() -> None:
    """ล้าง in-process cache ของ api ให้แต่ละเทสต์เริ่มสะอาด

    ก่อนแยก cache อยู่ใน backend.api · หลังแยก (Phase B) cache ของ market routes
    จะอยู่ใน backend.api.routes.market — เคลียร์ทั้งสองที่ถ้ามี
    """
    import importlib

    for mod_name in ("backend.api", "backend.api.routes.market"):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        for attr in ("_WATCHLIST_CACHE", "_CANDLE_CACHE", "_WATCHLIST_LIVE_CACHE"):
            cache = getattr(mod, attr, None)
            if isinstance(cache, dict):
                cache.clear()
        # _SYMBOLS_CACHE มีโครงสร้าง {"ts": float, "data": ...} — reset ตามรูปแบบเดิม
        symbols_cache = getattr(mod, "_SYMBOLS_CACHE", None)
        if isinstance(symbols_cache, dict) and "data" in symbols_cache:
            symbols_cache.update(ts=0.0, data=None)
