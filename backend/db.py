"""
db.py — SQLite storage หลักของทั้งโปรเจกต์

🔵 System 1 (Rule-Based Setup Engine)  → ตาราง setup_signals
🟢 System 2 (ML Model Engine)          → ตาราง ml_signals + ml_latest
ราคา/กราฟ (ใช้ร่วมกันทั้ง 2 ระบบ)      → ตาราง prices / ticks

ห้าม insert/update ข้าม schema กัน — Rule-Based แตะเฉพาะ setup_* functions,
ML แตะเฉพาะ ml_* functions เท่านั้น เพื่อรักษา Decoupled Architecture ตาม spec
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    from backend.deriv_feed import DEFAULT_SYMBOL
except ModuleNotFoundError:
    try:
        from backend.data_feed.deriv_feed import DEFAULT_SYMBOL
    except ModuleNotFoundError:
        DEFAULT_SYMBOL = "frxXAUUSD"

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bot.db"
DB_PATH.parent.mkdir(exist_ok=True)

MAX_PRICE_ROWS = 50000
MAX_TICK_ROWS = 10000


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()

    # 🟢 Migration: ตารางเก่าชื่อ "signals" (ยุคก่อนแยกระบบ ที่ทั้ง Rule-Based
    # และ ML เคย insert ชนกัน) → เปลี่ยนชื่อเป็น setup_signals เพื่อเก็บ
    # ประวัติเดิมไว้ (ข้อมูลเก่าเป็นของ Rule-Based เพราะ ML ยังไม่เคยเขียน DB จริง)
    existing = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "signals" in existing and "setup_signals" not in existing:
        conn.execute("ALTER TABLE signals RENAME TO setup_signals")
        conn.commit()

    conn.executescript(
        """
        -- RULE-BASED SETUP ENGINE ------------------------------------
        CREATE TABLE IF NOT EXISTS setup_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_time TEXT NOT NULL,
            timeframe TEXT DEFAULT 'M1',
            entry_price REAL NOT NULL,
            direction TEXT NOT NULL,
            confidence REAL NOT NULL,
            score INTEGER,
            total INTEGER,
            tier TEXT DEFAULT 'NONE',
            horizon_min INTEGER NOT NULL,
            target_time TEXT NOT NULL,
            exit_price REAL,
            result TEXT DEFAULT 'PENDING',
            phantom INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_setup_signals_time ON setup_signals(signal_time);
        CREATE INDEX IF NOT EXISTS idx_setup_signals_tf ON setup_signals(timeframe);
        CREATE INDEX IF NOT EXISTS idx_setup_signals_result ON setup_signals(result);

        -- ML MODEL ENGINE ----------------------------------------------
        CREATE TABLE IF NOT EXISTS ml_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_time TEXT NOT NULL,
            timeframe TEXT DEFAULT 'M1',
            entry_price REAL NOT NULL,
            direction TEXT NOT NULL,
            confidence REAL NOT NULL,
            prob_up REAL,
            prob_down REAL,
            threshold_used REAL,
            model_version TEXT,
            horizon_min INTEGER NOT NULL,
            target_time TEXT NOT NULL,
            exit_price REAL,
            result TEXT DEFAULT 'PENDING',
            features_json TEXT,
            phantom INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ml_signals_time ON ml_signals(signal_time);
        CREATE INDEX IF NOT EXISTS idx_ml_signals_tf ON ml_signals(timeframe);
        CREATE INDEX IF NOT EXISTS idx_ml_signals_result ON ml_signals(result);

        CREATE TABLE IF NOT EXISTS ml_latest (
            timeframe TEXT PRIMARY KEY,
            ts TEXT,
            prob_up REAL,
            prob_down REAL,
            signal TEXT,
            confidence REAL,
            threshold_used REAL
        );

        CREATE TABLE IF NOT EXISTS prices (
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT 'frxXAUUSD',
            open REAL, high REAL, low REAL, close REAL,
            PRIMARY KEY (ts, symbol)
        );

        CREATE TABLE IF NOT EXISTS ticks (
            timestamp TEXT PRIMARY KEY,
            price REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ticks_time ON ticks(timestamp);

        -- MACRO (DXY รายชั่วโมง — ใช้คำนวณ Regime-Gate ตอนยิงสัญญาณ) -----------
        CREATE TABLE IF NOT EXISTS macro_1h (
            ts TEXT PRIMARY KEY,
            dxy_close REAL
        );

        -- TRADE JOURNAL (บันทึกทุกออเดอร์จริง เพื่อตรวจสอบ/พัฒนาโมเดล) ---------
        CREATE TABLE IF NOT EXISTS trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            signal_type TEXT NOT NULL DEFAULT 'ML',   -- ML / SETUP
            timeframe TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT 'frxXAUUSD',
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            hold_min INTEGER NOT NULL,
            confidence REAL,
            model_version TEXT,
            result TEXT DEFAULT 'PENDING',            -- WIN / LOSE / PENDING
            pnl REAL,                                 -- ผลกำไร/ขาดทุน (ถ้าใช้ money จำลอง)
            payout REAL DEFAULT 0.82,
            win_amount REAL,
            loss_amount REAL,
            note TEXT,
            phantom INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_trade_journal_time ON trade_journal(entry_time);
        CREATE INDEX IF NOT EXISTS idx_trade_journal_tf ON trade_journal(timeframe);
        CREATE INDEX IF NOT EXISTS idx_trade_journal_result ON trade_journal(result);

        -- MODEL REGISTRY (ติดตาม version โมเดล ใช้ A/B เปรียบเทียบ) -----------
        CREATE TABLE IF NOT EXISTS model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_key TEXT NOT NULL,                  -- M1 / M5
            version TEXT NOT NULL,                    -- v2_meanrev
            trained_at TEXT NOT NULL,
            horizon INTEGER NOT NULL,
            n_rows INTEGER,
            auc_val REAL,
            auc_test REAL,
            chosen_conf REAL,
            feature_set TEXT,
            note TEXT,
            UNIQUE(model_key, version)
        );

        -- DAILY STATS (สรุปผลรายวัน ไว้ทำ P&L curve) ---------------------------
        CREATE TABLE IF NOT EXISTS daily_stats (
            day TEXT PRIMARY KEY,
            signal_type TEXT NOT NULL,                -- ML / SETUP / ALL
            n_trades INTEGER DEFAULT 0,
            n_wins INTEGER DEFAULT 0,
            pnl REAL DEFAULT 0,
            winrate REAL,
            updated_at TEXT
        );

        -- TRADING CONFIG (ทุน / ขนาดไม้ / สกุล — แก้ได้จากหน้าเว็บ) ----------
        CREATE TABLE IF NOT EXISTS trading_config (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(setup_signals)").fetchall()}
    if "timeframe" not in cols:
        conn.execute("ALTER TABLE setup_signals ADD COLUMN timeframe TEXT DEFAULT 'M1'")
    if "score" not in cols:
        conn.execute("ALTER TABLE setup_signals ADD COLUMN score INTEGER")
    if "total" not in cols:
        conn.execute("ALTER TABLE setup_signals ADD COLUMN total INTEGER")
    if "tier" not in cols:
        conn.execute("ALTER TABLE setup_signals ADD COLUMN tier TEXT DEFAULT 'NONE'")

    # Migration: ml_signals เก่า (ยุคก่อนเก็บ features ตอนยิง) → เพิ่ม features_json
    # เพื่อให้ auto_retrain เรียนจากสัญญาณจริงที่แพ้/ชนะพร้อม features ตอนนั้นได้
    mcols = {r["name"] for r in conn.execute("PRAGMA table_info(ml_signals)").fetchall()}
    if "features_json" not in mcols:
        conn.execute("ALTER TABLE ml_signals ADD COLUMN features_json TEXT")

    # Migration: รองรับการเทรดหลายสัญลักษณ์ (major pairs) → เพิ่มคอลัมน์ symbol
    # ข้อมูลเก่าถือเป็น frxXAUUSD (สัญลักษณ์เดิมที่ระบบเคยเทรด)
    scols = {r["name"] for r in conn.execute("PRAGMA table_info(setup_signals)").fetchall()}
    if "symbol" not in scols:
        conn.execute("ALTER TABLE setup_signals ADD COLUMN symbol TEXT NOT NULL DEFAULT 'frxXAUUSD'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_setup_signals_symbol ON setup_signals(symbol)")

    # Migration: บันทึกตำแหน่งราคาเทียบ EMA200 ตอนยิงสัญญาณ (ไว้วิเคราะห์ว่า
    # band ไหนของ EMA200 ให้ winrate ดีที่สุด และยืนยัน "ไม้ชนะ = แตะ EMA200")
    if "ema200_price" not in scols:
        for _c in ("ema200_price", "dist200_pct", "near_ema200", "crossed_ema100"):
            conn.execute(f"ALTER TABLE setup_signals ADD COLUMN {_c} REAL")
        conn.commit()

    # Migration: Regime-Gate (shadow mode) — บันทึก gold_1h_slope/dxy_slope_24/
    # dxy_rsi/gate_agree ตอนยิงสัญญาณ FIRE (ยังไม่บล็อก — เก็บสะสมผลจริงก่อนเปิดใช้)
    gcols = {r["name"] for r in conn.execute("PRAGMA table_info(setup_signals)").fetchall()}
    for _c in ("gold_slope_1h", "dxy_slope_24", "dxy_rsi", "gate_agree"):
        if _c not in gcols:
            conn.execute(f"ALTER TABLE setup_signals ADD COLUMN {_c} REAL")
    conn.commit()

    # Migration: phantom flag — กันสัญญาณผีออกจากสถิติ (เช่น 7 สัญญาณที่ยิงตอน
    # restart วันเสาร์ 2026-08-15 20:33 หลังตลาดปิด ราคา exit==entry เลยแพ้รวด
    # ซึ่งไม่ใช่การเทรดจริง) เก็บแถวไว้เป็น audit trail แต่ไม่นับใน winrate/P&L
    for _t in ("setup_signals", "ml_signals", "trade_journal"):
        _cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({_t})").fetchall()}
        if "phantom" not in _cols:
            conn.execute(f"ALTER TABLE {_t} ADD COLUMN phantom INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    _ph = conn.execute(
        "SELECT id FROM setup_signals "
        "WHERE signal_time >= '2026-08-15T20:33:40' AND signal_time <= '2026-08-15T20:34:00' "
        "AND result = 'LOSE' AND COALESCE(phantom, 0) = 0"
    ).fetchall()
    if _ph:
        _ids = [r["id"] for r in _ph]
        conn.executemany(
            "UPDATE setup_signals SET phantom = 1 WHERE id = ?",
            [(i,) for i in _ids],
        )
        conn.executemany(
            "UPDATE trade_journal SET phantom = 1 WHERE signal_id = ? AND signal_type = 'SETUP'",
            [(i,) for i in _ids],
        )
        conn.commit()

    # Migration: ตาราง prices เก่า (ยุคก่อนมีคอลัมน์ symbol) → เพิ่ม symbol
    # แล้วสมมติว่าแถวเก่าทั้งหมดเป็น frxXAUUSD (ข้อมูลกราฟเดิม)
    try:
        pcols = {r["name"] for r in conn.execute("PRAGMA table_info(prices)").fetchall()}
        if "symbol" not in pcols:
            conn.execute("ALTER TABLE prices ADD COLUMN symbol TEXT NOT NULL DEFAULT 'frxXAUUSD'")
            conn.commit()

        # Migration 2: ตารางเก่ายังมี PK = (ts) ตัวเดียว → XAUUSD กับ R_100 ที่
        # ts ตรงกันชนกัน (REPLACE ทับ) จนกราฟ scale เพี้ยน/ข้อมูลหาย
        # → rebuild เป็น PK (ts, symbol) เพื่อให้ 2 สัญลักษณ์อยู่ร่วมกันได้
        pk = [r[1] for r in conn.execute("PRAGMA table_info(prices)").fetchall()
              if r[5] == 1]
        if pk != ["ts", "symbol"]:
            conn.execute("""
                CREATE TABLE prices_new (
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL DEFAULT 'frxXAUUSD',
                    open REAL, high REAL, low REAL, close REAL,
                    PRIMARY KEY (ts, symbol)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO prices_new (ts, symbol, open, high, low, close)
                SELECT ts, symbol, open, high, low, close FROM prices
            """)
            conn.execute("DROP TABLE prices")
            conn.execute("ALTER TABLE prices_new RENAME TO prices")
            conn.commit()
    except Exception:
        pass

    conn.commit()
    conn.close()


# ── MACRO (DXY รายชั่วโมง — ข้อมูลสำหรับ Regime-Gate) ─────────────────────────
def upsert_macro_dxy(ts: str, dxy_close: float) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO macro_1h (ts, dxy_close) VALUES (?, ?) "
        "ON CONFLICT(ts) DO UPDATE SET dxy_close = excluded.dxy_close",
        (ts, float(dxy_close)),
    )
    conn.commit()
    conn.close()


def fetch_macro_dxy(limit: int = 96) -> list[dict]:
    """DXY รายชั่วโมง เก่า→ใหม่ (limit แถวล่าสุด) — ใช้คำนวณ slope/RSI ตอนยิงสัญญาณ"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM macro_1h ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def fetch_latest_macro_dxy() -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM macro_1h ORDER BY ts DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


# RULE-BASED SETUP SIGNALS
def insert_setup_signal(signal_time: str, entry_price: float, direction: str,
                         confidence: float, horizon_min: int, target_time: str,
                         timeframe: str = "M1", score: Optional[float] = None,
                         total: Optional[int] = None, tier: str = "NONE",
                         symbol: str = "frxXAUUSD",
                         ema200_price: Optional[float] = None,
                         dist200_pct: Optional[float] = None,
                         near_ema200: Optional[bool] = None,
                         crossed_ema100: Optional[bool] = None,
                         gold_slope_1h: Optional[float] = None,
                         dxy_slope_24: Optional[float] = None,
                         dxy_rsi: Optional[float] = None,
                         gate_agree: Optional[bool] = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO setup_signals
           (signal_time, timeframe, entry_price, direction, confidence,
            score, total, tier, horizon_min, target_time, result, symbol,
            ema200_price, dist200_pct, near_ema200, crossed_ema100,
            gold_slope_1h, dxy_slope_24, dxy_rsi, gate_agree)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?,
                   ?, ?, ?, ?)""",
        (signal_time, timeframe, entry_price, direction, confidence,
         score, total, tier, horizon_min, target_time, symbol,
         ema200_price, dist200_pct,
         (1 if near_ema200 else 0) if near_ema200 is not None else None,
         (1 if crossed_ema100 else 0) if crossed_ema100 is not None else None,
         gold_slope_1h, dxy_slope_24, dxy_rsi,
         (1 if gate_agree else 0) if gate_agree is not None else None),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_setup_signal_result(signal_id: int, exit_price: float, result: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE setup_signals SET exit_price = ?, result = ? WHERE id = ?",
        (exit_price, result, signal_id),
    )
    conn.commit()
    conn.close()


def fetch_pending_setup_signals(symbol: str | None = None) -> list[dict]:
    conn = get_conn()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM setup_signals WHERE result = 'PENDING' AND symbol = ?",
            (symbol,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM setup_signals WHERE result = 'PENDING'"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_recent_setup_signals(limit: int = 100, symbol: str | None = None) -> list[dict]:
    conn = get_conn()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM setup_signals WHERE symbol = ? ORDER BY signal_time DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM setup_signals ORDER BY signal_time DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_last_setup_signal(timeframe: str, symbol: str | None = None) -> dict | None:
    """สัญญาณล่าสุดของ TF นี้ (สำหรับ cooldown — กันยิงซ้ำหลัง restart)"""
    conn = get_conn()
    if symbol:
        row = conn.execute(
            "SELECT * FROM setup_signals WHERE timeframe = ? AND symbol = ? "
            "ORDER BY signal_time DESC LIMIT 1",
            (timeframe, symbol),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM setup_signals WHERE timeframe = ? ORDER BY signal_time DESC LIMIT 1",
            (timeframe,),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def count_setup_signals_since(start_iso: str, symbol: str | None = None) -> int:
    """จำนวนสัญญาณที่ยิงตั้งแต่เวลา start_iso (ใช้สำหรับ daily cap)"""
    conn = get_conn()
    if start_iso:
        if symbol:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM setup_signals "
                "WHERE signal_time >= ? AND symbol = ?",
                (start_iso, symbol),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM setup_signals WHERE signal_time >= ?",
                (start_iso,),
            ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) AS c FROM setup_signals").fetchone()
    conn.close()
    return int(row["c"])


def compute_setup_stats(payout: float = 0.82) -> dict:
    return _compute_stats("setup_signals", payout)


def compute_setup_stats_by_timeframe(payout: float = 0.82) -> dict:
    return _compute_stats_by_timeframe("setup_signals", payout)


# ML MODEL SIGNALS
def insert_ml_signal(signal_time: str, entry_price: float, direction: str,
                      confidence: float, horizon_min: int, target_time: str,
                      timeframe: str = "M1", prob_up: Optional[float] = None,
                      prob_down: Optional[float] = None,
                      threshold_used: Optional[float] = None,
                      model_version: Optional[str] = None,
                      features: Optional[dict] = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO ml_signals
           (signal_time, timeframe, entry_price, direction, confidence,
            prob_up, prob_down, threshold_used, model_version,
            horizon_min, target_time, result, features_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
        (signal_time, timeframe, entry_price, direction, confidence,
         prob_up, prob_down, threshold_used, model_version,
         horizon_min, target_time,
         json.dumps(features) if features is not None else None),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_ml_signal_result(signal_id: int, exit_price: float, result: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE ml_signals SET exit_price = ?, result = ? WHERE id = ?",
        (exit_price, result, signal_id),
    )
    conn.commit()
    conn.close()


def fetch_pending_ml_signals() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ml_signals WHERE result = 'PENDING'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_recent_ml_signals(limit: int = 100) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ml_signals ORDER BY signal_time DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_ml_stats(payout: float = 0.82) -> dict:
    return _compute_stats("ml_signals", payout)


def compute_ml_stats_by_timeframe(payout: float = 0.82) -> dict:
    return _compute_stats_by_timeframe("ml_signals", payout)


def upsert_ml_latest(timeframe: str, ts: str, prob_up: float, prob_down: float,
                      signal: str, confidence: float, threshold_used: float) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO ml_latest (timeframe, ts, prob_up, prob_down, signal, confidence, threshold_used)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(timeframe) DO UPDATE SET
             ts=excluded.ts, prob_up=excluded.prob_up, prob_down=excluded.prob_down,
             signal=excluded.signal, confidence=excluded.confidence,
             threshold_used=excluded.threshold_used""",
        (timeframe, ts, prob_up, prob_down, signal, confidence, threshold_used),
    )
    conn.commit()
    conn.close()


def fetch_ml_latest() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM ml_latest").fetchall()
    conn.close()
    return {r["timeframe"]: dict(r) for r in rows}


# PRICES / TICKS (shared)
def insert_price(ts: str, open_: float, high: float, low: float, close: float,
                 symbol: str | None = None) -> None:
    symbol = symbol or DEFAULT_SYMBOL
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO prices (ts, symbol, open, high, low, close) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, symbol, open_, high, low, close),
    )
    conn.execute(
        """DELETE FROM prices WHERE ts NOT IN (
             SELECT ts FROM prices WHERE symbol = ? ORDER BY ts DESC LIMIT ?
           )""",
        (symbol, MAX_PRICE_ROWS),
    )
    conn.commit()
    conn.close()


def backfill_prices(candles, symbol: str | None = None) -> int:
    """เขียนแท่งเทียนย้อนหลังทั้งชุดลง prices ครั้งเดียว (ตอนเริ่มระบบ)

    เดิมทั้ง setup_feed/notifier แทรกแค่ "แท่งสุดท้าย" ต่อ poll → บนเครื่องใหม่
    (เช่น VPS เพิ่ง boot) ตาราง prices จะว่างเปล่าแล้วค่อยๆ งอกทีละแท่ง
    ทำให้กราฟ Dashboard แท่งเทียนว่าง/ไม่เต็มกรอบไปหลายชั่วโมง
    ฟังก์ชันนี้ bulk เขียนทุกแท่งใน buffer (เฉพาะที่ยังไม่มีในตาราง) ให้กราฟ
    มีประวัติทันที ใช้ INSERT OR REPLACE เพื่อให้ค่าแท่งล่าสุดถูกเสมอ
    """
    if candles is None or len(candles) == 0:
        return 0
    symbol = symbol or DEFAULT_SYMBOL
    rows = []
    for ts, r in candles.iterrows():
        ts_iso = pd.Timestamp(ts).isoformat()
        rows.append((ts_iso, symbol, float(r["open"]), float(r["high"]),
                     float(r["low"]), float(r["close"])))
    if not rows:
        return 0

    conn = get_conn()
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO prices (ts, symbol, open, high, low, close) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute(
            """DELETE FROM prices WHERE ts NOT IN (
                 SELECT ts FROM prices WHERE symbol = ? ORDER BY ts DESC LIMIT ?
               )""",
            (symbol, MAX_PRICE_ROWS),
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def insert_tick(timestamp_iso: str, price: float) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO ticks (timestamp, price) VALUES (?, ?)",
        (timestamp_iso, price),
    )
    conn.execute(
        """DELETE FROM ticks WHERE timestamp NOT IN (
             SELECT timestamp FROM ticks ORDER BY timestamp DESC LIMIT ?
           )""",
        (MAX_TICK_ROWS,),
    )
    conn.commit()
    conn.close()


def fetch_recent_prices(limit: int = 500, symbol: str | None = None) -> list[dict]:
    symbol = symbol or DEFAULT_SYMBOL
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM prices WHERE symbol = ? ORDER BY ts DESC LIMIT ?", (symbol, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows][::-1]


# STATS HELPERS
def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z ** 2 / n
    center = p + z ** 2 / (2 * n)
    margin = z * ((p * (1 - p) / n + z ** 2 / (4 * n ** 2)) ** 0.5)
    lo = (center - margin) / denom
    hi = (center + margin) / denom
    return round(lo * 100, 2), round(hi * 100, 2)


_ALLOWED_TABLES = {"setup_signals", "ml_signals"}


def _compute_stats(table: str, payout: float = 0.82) -> dict:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"table ไม่ถูกต้อง: {table}")
    conn = get_conn()
    row = conn.execute(
        f"""SELECT
             COUNT(*) FILTER (WHERE result != 'PENDING' AND COALESCE(phantom, 0) = 0) AS n_resolved,
             COUNT(*) FILTER (WHERE result = 'WIN' AND COALESCE(phantom, 0) = 0) AS wins,
             COUNT(*) FILTER (WHERE result = 'LOSE' AND COALESCE(phantom, 0) = 0) AS losses,
             COUNT(*) FILTER (WHERE result = 'DRAW' AND COALESCE(phantom, 0) = 0) AS draws,
             COUNT(*) FILTER (WHERE result = 'PENDING') AS n_pending
           FROM {table}"""
    ).fetchone()
    conn.close()

    n = row["n_resolved"] or 0
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    draws = row["draws"] or 0
    decided = wins + losses
    winrate = round(100 * wins / decided, 2) if decided else 0.0
    ci_low, ci_high = wilson_ci(wins, decided)
    breakeven = round(1 / (1 + payout) * 100, 2)
    margin = round(ci_low - breakeven, 2)

    return {
        "n_resolved": n, "wins": wins, "losses": losses, "draws": draws,
        "n_pending": row["n_pending"] or 0,
        "winrate": winrate, "ci_low": ci_low, "ci_high": ci_high,
        "breakeven": breakeven, "margin": margin, "payout": payout,
    }


def _compute_stats_by_timeframe(table: str, payout: float = 0.82) -> dict:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"table ไม่ถูกต้อง: {table}")
    conn = get_conn()
    rows = conn.execute(
        f"""SELECT
             COALESCE(timeframe, 'M1') AS tf,
             COUNT(*) FILTER (WHERE result != 'PENDING' AND COALESCE(phantom, 0) = 0) AS n_resolved,
             COUNT(*) FILTER (WHERE result = 'WIN' AND COALESCE(phantom, 0) = 0) AS wins,
             COUNT(*) FILTER (WHERE result = 'LOSE' AND COALESCE(phantom, 0) = 0) AS losses,
             COUNT(*) FILTER (WHERE result = 'DRAW' AND COALESCE(phantom, 0) = 0) AS draws,
             COUNT(*) FILTER (WHERE result = 'PENDING') AS n_pending
           FROM {table}
           GROUP BY tf"""
    ).fetchall()
    conn.close()

    breakeven = round(1 / (1 + payout) * 100, 2)
    out = {}
    for r in rows:
        n = r["n_resolved"] or 0
        wins = r["wins"] or 0
        losses = r["losses"] or 0
        draws = r["draws"] or 0
        decided = wins + losses
        winrate = round(100 * wins / decided, 2) if decided else 0.0
        ci_low, ci_high = wilson_ci(wins, decided)
        margin = round(ci_low - breakeven, 2)
        out[r["tf"]] = {
            "n_resolved": n, "wins": wins, "losses": losses, "draws": draws,
            "n_pending": r["n_pending"] or 0,
            "winrate": winrate, "ci_low": ci_low, "ci_high": ci_high,
            "breakeven": breakeven, "margin": margin, "payout": payout,
        }
    return out


# ─── TRADE JOURNAL ───────────────────────────────────────────────────────────

def insert_trade(signal_id: int, signal_type: str, timeframe: str, symbol: str,
                 direction: str, entry_price: float, entry_time: str,
                 hold_min: int, confidence: float | None = None,
                 model_version: str | None = None,
                 payout: float = 0.82) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO trade_journal
           (signal_id, signal_type, timeframe, symbol, direction, entry_price,
            entry_time, hold_min, confidence, model_version, payout, result)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')""",
        (signal_id, signal_type, timeframe, symbol, direction, entry_price,
         entry_time, hold_min, confidence, model_version, payout),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_trade_result(trade_id: int, exit_price: float, exit_time: str,
                        result: str) -> None:
    """บันทึกผล WIN/LOSE + pnl จำลอง (win = +1 unit, lose = -1 unit ของ payout)"""
    conn = get_conn()
    row = conn.execute(
        "SELECT direction, payout FROM trade_journal WHERE id = ?", (trade_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return
    pnl = row["payout"] if result == "WIN" else (-1.0 if result == "LOSE" else 0.0)
    conn.execute(
        """UPDATE trade_journal SET exit_price = ?, exit_time = ?, result = ?,
           pnl = ?, win_amount = CASE WHEN ? = 'WIN' THEN ? ELSE 0 END,
           loss_amount = CASE WHEN ? = 'LOSE' THEN 1 ELSE 0 END
           WHERE id = ?""",
        (exit_price, exit_time, result, pnl, result, row["payout"], result, trade_id),
    )
    conn.commit()
    conn.close()


def fetch_recent_trades(limit: int = 100, signal_type: str | None = None) -> list[dict]:
    conn = get_conn()
    sql = "SELECT * FROM trade_journal"
    params: list = []
    if signal_type:
        sql += " WHERE signal_type = ?"
        params.append(signal_type)
    sql += " ORDER BY entry_time DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_journal_stats(payout: float = 0.82) -> dict:
    """P&L รวม / winrate / equity curve จำลอง จาก trade_journal ทั้งหมด"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trade_journal WHERE result IN ('WIN', 'LOSE') AND COALESCE(phantom, 0) = 0 "
        "ORDER BY exit_time"
    ).fetchall()
    conn.close()
    rows = [dict(r) for r in rows]

    n = len(rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    total_pnl = sum(r["pnl"] or 0 for r in rows)
    winrate = round(100 * wins / n, 2) if n else 0.0
    ci_low, ci_high = wilson_ci(wins, n)
    breakeven = round(1 / (1 + payout) * 100, 2)

    # equity curve (cumulative pnl)
    equity = []
    cum = 0.0
    for r in rows:
        cum += r["pnl"] or 0
        equity.append({"t": r["exit_time"], "equity": round(cum, 4)})

    # daily breakdown
    daily: dict[str, dict] = {}
    for r in rows:
        day = (r["exit_time"] or r["entry_time"])[:10]
        d = daily.setdefault(day, {"day": day, "n": 0, "wins": 0, "pnl": 0.0})
        d["n"] += 1
        d["wins"] += 1 if r["result"] == "WIN" else 0
        d["pnl"] += r["pnl"] or 0

    daily_list = sorted(daily.values(), key=lambda x: x["day"], reverse=True)
    for d in daily_list:
        d["winrate"] = round(100 * d["wins"] / d["n"], 2) if d["n"] else 0.0
        d["pnl"] = round(d["pnl"], 4)

    return {
        "n": n, "wins": wins, "losses": n - wins,
        "winrate": winrate, "ci_low": ci_low, "ci_high": ci_high,
        "breakeven": breakeven, "total_pnl": round(total_pnl, 4),
        "equity": equity[-200:], "daily": daily_list[:30],
    }


# ─── MODEL REGISTRY ──────────────────────────────────────────────────────────

def register_model(model_key: str, version: str, trained_at: str, horizon: int,
                   n_rows: int | None, auc_val: float | None, auc_test: float | None,
                   chosen_conf: float | None, feature_set: str | None = None,
                   note: str | None = None) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO model_registry
           (model_key, version, trained_at, horizon, n_rows, auc_val, auc_test,
            chosen_conf, feature_set, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(model_key, version) DO UPDATE SET
             trained_at=excluded.trained_at, n_rows=excluded.n_rows,
             auc_val=excluded.auc_val, auc_test=excluded.auc_test,
             chosen_conf=excluded.chosen_conf, feature_set=excluded.feature_set,
             note=excluded.note""",
        (model_key, version, trained_at, horizon, n_rows, auc_val, auc_test,
         chosen_conf, feature_set, note),
    )
    conn.commit()
    conn.close()


def fetch_model_registry(limit: int = 20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM model_registry ORDER BY trained_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── DAILY STATS (P&L curve) ─────────────────────────────────────────────────

def upsert_daily_stat(day: str, signal_type: str, n_trades: int, n_wins: int,
                      pnl: float) -> None:
    conn = get_conn()
    winrate = round(100 * n_wins / n_trades, 2) if n_trades else 0.0
    conn.execute(
        """INSERT INTO daily_stats (day, signal_type, n_trades, n_wins, pnl, winrate, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(day, signal_type) DO UPDATE SET
             n_trades=excluded.n_trades, n_wins=excluded.n_wins,
             pnl=excluded.pnl, winrate=excluded.winrate, updated_at=excluded.updated_at""",
        (day, signal_type, n_trades, n_wins, pnl, winrate,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


# ─── TRADING CONFIG (ทุน / ขนาดไม้ / สกุลเงิน) ───────────────────────────────

def get_config(key: str, default: str | None = None) -> str | None:
    conn = get_conn()
    row = conn.execute("SELECT value FROM trading_config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_config(key: str, value) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO trading_config (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def fetch_trading_settings() -> dict:
    """ค่า config ปัจจุบัน (capital / stake / currency) — ตั้ง default ถ้ายังไม่เคยตั้ง"""
    capital = get_config("capital", "5000")
    stake = get_config("stake", "100")
    currency = get_config("currency", "THB")
    if get_config("capital") is None:
        set_config("capital", 5000)
    if get_config("stake") is None:
        set_config("stake", 100)
    if get_config("currency") is None:
        set_config("currency", "THB")
    return {"capital": float(capital), "stake": float(stake),
            "currency": currency or "THB"}


# ─── MONEY REPORT (P&L เป็นเงิน — แยก ML / SETUP) ────────────────────────────

def _period_keys(ts: str) -> tuple[str, str, str, str]:
    """แยก timestamp → (day, week, month, year) รองรับทั้ง ISO และ 'YYYY-MM-DD'"""
    ts = (ts or "")[:10]
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d")
        iso = dt.isocalendar()
        return ts, f"{iso.year}-W{iso.week:02d}", ts[:7], str(iso.year)
    except ValueError:
        return ts, ts, ts, ts


def compute_money_report(start: str | None = None, end: str | None = None) -> dict:
    """รายงาน P&L แยกตามระบบ (ALL/ML/SETUP) รายวัน/สัปดาห์/เดือน/ปี โดยคิดเป็นเงิน
    จริงจาก stake: win = +stake×payout, lose = −stake.
    ระบุ start/end ('YYYY-MM-DD') เพื่อกรองเฉพาะช่วงเวลา"""
    capital, stake, currency = (
        fetch_trading_settings()["capital"],
        fetch_trading_settings()["stake"],
        fetch_trading_settings()["currency"],
    )

    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trade_journal WHERE result IN ('WIN', 'LOSE') AND COALESCE(phantom, 0) = 0 "
        "ORDER BY exit_time"
    ).fetchall()
    conn.close()

    recs = []
    for r in rows:
        d = dict(r)
        day, week, month, year = _period_keys(d.get("exit_time") or d.get("entry_time") or "")
        if start and day < start:
            continue
        if end and day > end:
            continue
        recs.append({
            "sys": d.get("signal_type") or "ML",
            "day": day, "week": week, "month": month, "year": year,
            "pnl": d.get("pnl") or 0,
            "win": 1 if d.get("result") == "WIN" else 0,
        })

    def agg(sub) -> dict:
        n = len(sub)
        wins = sum(x["win"] for x in sub)
        units = sum(x["pnl"] for x in sub)
        return {
            "n": n, "wins": wins, "losses": n - wins,
            "winrate": round(100 * wins / n, 2) if n else 0.0,
            "pnl_units": round(units, 4),
            "pnl_money": round(units * stake, 2),
            "roi": round(100 * units * stake / capital, 2) if capital else 0.0,
        }

    # group recs by period
    by_period: dict[str, dict[str, list]] = {
        "day": {}, "week": {}, "month": {}, "year": {},
    }
    for i, r in enumerate(recs):
        for kind, key in (("day", r["day"]), ("week", r["week"]),
                          ("month", r["month"]), ("year", r["year"])):
            by_period[kind].setdefault(key, []).append(i)

    def build(kind, key_of) -> list[dict]:
        out = []
        for key, idxs in by_period[kind].items():
            sub = [recs[i] for i in idxs]
            row = {"period": key, "key": key_of(key)}
            for s in ("ALL", "ML", "SETUP"):
                if s != "ALL":
                    filtered = [x for x in sub if x["sys"] == s]
                else:
                    filtered = sub
                a = agg(filtered)
                row[s] = a
            out.append(row)
        # balance สะสมของ ALL (เป็นเงิน)
        out.sort(key=lambda x: x["key"])
        cum = 0.0
        for row in out:
            cum += row["ALL"]["pnl_money"]
            row["balance"] = round(capital + cum, 2)
        return out

    def summary() -> dict:
        out = {}
        for s in ("ALL", "ML", "SETUP"):
            sub = recs if s == "ALL" else [x for x in recs if x["sys"] == s]
            a = agg(sub)
            out[s] = a
        return out

    return {
        "settings": {"capital": capital, "stake": stake, "currency": currency},
        "summary": summary(),
        "daily": build("day", lambda k: k),
        "weekly": build("week", lambda k: k),
        "monthly": build("month", lambda k: k),
        "yearly": build("year", lambda k: k),
    }


if __name__ == "__main__":
    init_db()
    print(f"[db] สร้าง/เช็คตารางเรียบร้อยที่ {DB_PATH}")
