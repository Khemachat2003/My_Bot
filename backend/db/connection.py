"""db.connection — SQLite connection กลางของโปรเจกต์ (ย้ายจาก db.py แบบ move-only)

⚠️ ระบบรันหลาย process บนไฟล์ SQLite เดียว (WAL) — ห้ามเปลี่ยนรูปแบบการเปิด
connection นี้ (ดู backend/AGENTS.md) · tests patch DB_PATH ของ module นี้โดยตรง
(tests/conftest.py → _conn_module)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "bot.db"
DB_PATH.parent.mkdir(exist_ok=True)

MAX_PRICE_ROWS = 50000
MAX_TICK_ROWS = 10000


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn
