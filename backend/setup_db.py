"""
setup_db.py — เก็บผล setup_scorer (checklist 1m/5m) ลง sqlite ไฟล์เดียวกับ bot.db

แยกตารางออกจาก signals (ที่เป็นผลของโมเดล ML ใน db.py) เพราะคนละระบบกันตามที่
คุยไว้ใน setup_scorer.py — เอาไว้เทียบ/คอนเฟิร์มกันได้ แต่ไม่ผสม schema กัน

ไฟล์นี้เปิด connection ของตัวเอง (WAL mode เหมือน db.py) เขียน/อ่านพร้อมกันได้
ไม่ต้องแก้ db.py เดิม — ถ้าอยากรวมเข้า db.py ทีหลังก็ copy ฟังก์ชันไปวางได้เลย
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from backend.json_safe import to_json_safe

if TYPE_CHECKING:
    from backend.setup_scorer import SetupResult

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "bot.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_setup_db() -> None:
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS setup_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            score REAL NOT NULL,
            total INTEGER NOT NULL,
            direction TEXT,
            bias TEXT,
            entry_trigger INTEGER NOT NULL,
            entry_trigger_note TEXT,
            details_json TEXT NOT NULL,
            grip_json TEXT,
            tier TEXT DEFAULT 'NONE',
            max_score INTEGER DEFAULT 15
        )
    """)
    # Migration: ตารางเก่าที่ยังไม่มีคอลัมน์ใหม่
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(setup_scores)").fetchall()}
    if "tier" not in cols:
        conn.execute("ALTER TABLE setup_scores ADD COLUMN tier TEXT DEFAULT 'NONE'")
    if "max_score" not in cols:
        conn.execute("ALTER TABLE setup_scores ADD COLUMN max_score INTEGER DEFAULT 15")
    # รองรับหลายสัญลักษณ์ (major pairs) — ข้อมูลเก่าเป็น frxXAUUSD
    if "symbol" not in cols:
        conn.execute("ALTER TABLE setup_scores ADD COLUMN symbol TEXT NOT NULL DEFAULT 'frxXAUUSD'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_setup_scores_symbol ON setup_scores(symbol)")
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_setup_scores_tf_ts
        ON setup_scores (timeframe, id DESC)
    """)
    conn.commit()
    conn.close()


def insert_setup_score(ts: str, result: "SetupResult",
                       symbol: str = "frxXAUUSD") -> int:
    """result: SetupResult ที่ได้จาก setup_scorer.score_setup(...)"""
    details_serializable = result.details
    conn = _connect()
    cur = conn.execute("""
        INSERT INTO setup_scores
            (ts, timeframe, score, total, direction, bias,
             entry_trigger, entry_trigger_note, details_json, grip_json,
             tier, max_score, symbol)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ts, result.timeframe, result.score, result.max_score,
        result.direction, result.bias,
        int(result.entry_trigger), result.entry_trigger_note,
        json.dumps(to_json_safe(details_serializable), ensure_ascii=False),
        json.dumps(to_json_safe(result.grip_hits), ensure_ascii=False),
        result.tier, result.max_score,
        symbol,
    ))
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def _row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "ts": r["ts"],
        "timeframe": r["timeframe"],
        "score": r["score"],
        "total": r["total"],
        "direction": r["direction"],
        "bias": r["bias"],
        "entry_trigger": bool(r["entry_trigger"]),
        "entry_trigger_note": r["entry_trigger_note"],
        "details": json.loads(r["details_json"]),
        "grip_hits": json.loads(r["grip_json"]) if r["grip_json"] else [],
        "tier": r["tier"],
        "max_score": r["max_score"],
        "symbol": r["symbol"],
    }


def fetch_latest_setup_scores(symbol: str | None = None) -> dict:
    """คืนค่าล่าสุดของแต่ละ timeframe ของ symbol → {"1m": {...}, "5m": {...}}
    (ไม่ระบุ symbol = เอาล่าสุดข้ามทุกสัญลักษณ์)"""
    conn = _connect()
    if symbol:
        rows = conn.execute("""
            SELECT * FROM setup_scores
            WHERE symbol = ?
              AND id IN (SELECT MAX(id) FROM setup_scores
                         WHERE symbol = ? GROUP BY timeframe)
        """, (symbol, symbol)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM setup_scores
            WHERE id IN (SELECT MAX(id) FROM setup_scores GROUP BY timeframe)
        """).fetchall()
    conn.close()
    return {r["timeframe"]: _row_to_dict(r) for r in rows}


def fetch_recent_setup_scores(timeframe: str, limit: int = 50,
                              symbol: str | None = None) -> list[dict]:
    conn = _connect()
    if symbol:
        rows = conn.execute("""
            SELECT * FROM setup_scores
            WHERE timeframe = ? AND symbol = ?
            ORDER BY id DESC LIMIT ?
        """, (timeframe, symbol, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM setup_scores
            WHERE timeframe = ?
            ORDER BY id DESC LIMIT ?
        """, (timeframe, limit)).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in reversed(rows)]


def fetch_setup_scores_range(timeframe: str, start: str | None = None,
                             end: str | None = None,
                             symbol: str | None = None) -> list[dict]:
    """ดึง setup_scores ทั้งหมดของ timeframe ในช่วงเวลา (สำหรับ auto_retrain)
    — flatten details (10 checklist) ให้เป็นคอลัมน์ง่าย ๆ สำหรับ merge กับราคา
    default symbol=None = ทุกสัญลักษณ์ (แต่ auto_retrain ควรส่ง symbol=frxXAUUSD)"""
    q = "SELECT * FROM setup_scores WHERE timeframe = ?"
    params: list = [timeframe]
    if symbol:
        q += " AND symbol = ?"
        params.append(symbol)
    if start:
        q += " AND ts >= ?"
        params.append(start)
    if end:
        q += " AND ts <= ?"
        params.append(end)
    q += " ORDER BY ts ASC"
    conn = _connect()
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]
