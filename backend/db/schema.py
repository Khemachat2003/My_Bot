"""init_db + migration — ย้ายมาจาก backend/db.py เดิม (Phase B move-only)"""

from __future__ import annotations

from backend.db.cfd import _backfill_cfd_paper_trades
from backend.db.connection import get_conn


def init_db() -> None:
    conn = get_conn()

    # 🟢 Migration: ตารางเก่าชื่อ "signals" (ยุคก่อนแยกระบบ ที่ทั้ง Rule-Based
    # และ ML เคย insert ชนกัน) → เปลี่ยนชื่อเป็น setup_signals เพื่อเก็บ
    # ประวัติเดิมไว้ (ข้อมูลเก่าเป็นของ Rule-Based เพราะ ML ยังไม่เคยเขียน DB จริง)
    existing = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
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

        -- ราคา: index สำหรับ "ราคาล่าสุดของหลาย symbol" (watchlist)
        -- เดิมมีแต่ autoindex (ts, symbol) → ถ้ากรองด้วย symbol ต้องสแกนทั้งตาราง
        CREATE INDEX IF NOT EXISTS idx_prices_symbol_ts ON prices(symbol, ts DESC);

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

        -- CFD PAPER TRADING (จำลอง SL/TP แบบ realtime alongside binary signals) ---
        CREATE TABLE IF NOT EXISTS cfd_paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            signal_type TEXT NOT NULL,          -- SETUP / ML
            symbol TEXT NOT NULL DEFAULT 'frxXAUUSD',
            direction TEXT NOT NULL,            -- CALL / PUT
            entry_price REAL NOT NULL,
            entry_time TEXT NOT NULL,
            sl_price REAL NOT NULL,
            tp1_price REAL NOT NULL,
            tp2_price REAL NOT NULL,
            effective_entry REAL NOT NULL,
            lot_size REAL NOT NULL,
            pip_size REAL NOT NULL,
            spread_pips REAL NOT NULL,
            result TEXT DEFAULT 'OPEN',         -- OPEN / SL / TP1 / TP2 / TIMEOUT
            exit_price REAL,
            exit_time TEXT,
            pnl REAL,
            hold_bars INTEGER DEFAULT 0,
            tp1_hit INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cfd_paper_time ON cfd_paper_trades(entry_time);
        CREATE INDEX IF NOT EXISTS idx_cfd_paper_result ON cfd_paper_trades(result);
        CREATE INDEX IF NOT EXISTS idx_cfd_paper_open ON cfd_paper_trades(result) WHERE result = 'OPEN';

        -- TICK TOUCH RESEARCH LOG (เก็บข้อมูล 3 เคสแตะ EMA200 + checklist vote หา winrate) ---
        CREATE TABLE IF NOT EXISTS tick_touch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_time TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT 'frxXAUUSD',
            touch_case TEXT NOT NULL,           -- TICK_TOUCH / WICK_BOUNCE / BREAKOUT
            direction TEXT NOT NULL,            -- CALL / PUT
            entry_price REAL NOT NULL,
            ema200_price REAL NOT NULL,
            horizon_min INTEGER NOT NULL DEFAULT 30,
            target_time TEXT NOT NULL,
            conditions_json TEXT NOT NULL,      -- 10 conditions {key:{pass,note}}
            passed_count INTEGER NOT NULL DEFAULT 0,
            result TEXT DEFAULT 'PENDING',      -- PENDING / WIN / LOSE / DRAW
            exit_price REAL,
            exit_time TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ttl_symbol_time ON tick_touch_log(symbol, signal_time);
        CREATE INDEX IF NOT EXISTS idx_ttl_result ON tick_touch_log(result);

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
        conn.execute(
            "ALTER TABLE setup_signals ADD COLUMN symbol TEXT NOT NULL DEFAULT 'frxXAUUSD'"
        )
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

    # Migration: V8 — เก็บ importance + conditions_log ลง setup_signals
    # เพื่อวิเคราะห์ว่า checklist ตัวไหนมีน้ำหนักจริง (importance1 ยิงทันทีแต่เก็บ log
    # ทุก conditions ไว้ — เมื่อรู้ผล WIN/LOSE จะคำนวณ feature importance ได้)
    scols2 = {r["name"] for r in conn.execute("PRAGMA table_info(setup_signals)").fetchall()}
    for _c in ("importance", "conditions_passed"):
        if _c not in scols2:
            conn.execute(f"ALTER TABLE setup_signals ADD COLUMN {_c} INTEGER")
    if "conditions_log_json" not in scols2:
        conn.execute("ALTER TABLE setup_signals ADD COLUMN conditions_log_json TEXT")
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
        # ⚠️ ต้องเก็บ "ทุกคอลัมน์ที่เป็น PK" เรียงตามลำดับ
        #    ถ้าเอาแค่ pk==1 จะได้ ['ts'] เสมอ → เงื่อนไขไม่เคยเป็นจริง
        #    → rebuild ตาราง prices ทั้งตารางทุกครั้งที่ start (และดัน index ทิ้ง)
        pk = [
            r["name"]
            for r in sorted(
                (r for r in conn.execute("PRAGMA table_info(prices)").fetchall() if r["pk"]),
                key=lambda r: r["pk"],
            )
        ]
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

    # Migration: cleanup สัญญาณ TICK ที่ยิงรั่ว + CFD trades ที่ผิด
    try:
        conn2 = get_conn()
        # เพิ่มคอลัมน์ tp1_hit ถ้ายังไม่มี
        cfd_cols = {r[1] for r in conn2.execute("PRAGMA table_info(cfd_paper_trades)").fetchall()}
        if "tp1_hit" not in cfd_cols:
            conn2.execute("ALTER TABLE cfd_paper_trades ADD COLUMN tp1_hit INTEGER DEFAULT 0")

        # ── ลบ trade_journal จาก TICK ก่อน (ต้องทำก่อนลบ setup_signals) ──
        bad_tj = conn2.execute(
            "SELECT COUNT(*) FROM trade_journal WHERE timeframe = 'TICK'"
        ).fetchone()[0]
        if bad_tj:
            conn2.execute("DELETE FROM trade_journal WHERE timeframe = 'TICK'")
            print(f"[DB] Migration: ลบ {bad_tj} trade_journal entries (TICK)")
        bad_tj2 = conn2.execute(
            """SELECT COUNT(*) FROM trade_journal
               WHERE signal_id IN (SELECT id FROM setup_signals WHERE timeframe = 'TICK')"""
        ).fetchone()[0]
        if bad_tj2:
            conn2.execute(
                """DELETE FROM trade_journal
                   WHERE signal_id IN (SELECT id FROM setup_signals WHERE timeframe = 'TICK')"""
            )
            print(f"[DB] Migration: ลบ {bad_tj2} trade_journal entries (via signal_id → TICK)")
        bad_trades = conn2.execute(
            "SELECT COUNT(*) FROM trade_journal WHERE signal_type NOT IN ('ML','SETUP')"
        ).fetchone()[0]
        if bad_trades:
            conn2.execute("DELETE FROM trade_journal WHERE signal_type NOT IN ('ML','SETUP')")
            print(f"[DB] Migration: ลบ {bad_trades} trade_journal entries (ไม่ใช่ ML/SETUP)")

        # ── ลบ CFD trades ที่ผูกกับ TICK signals ──
        conn2.execute(
            """DELETE FROM cfd_paper_trades
               WHERE signal_id IN (
                   SELECT id FROM setup_signals WHERE timeframe = 'TICK'
               )"""
        )
        # ลบ TICK signals ทั้งหมด
        tick_count = conn2.execute(
            "SELECT COUNT(*) FROM setup_signals WHERE timeframe = 'TICK'"
        ).fetchone()[0]
        conn2.execute("DELETE FROM setup_signals WHERE timeframe = 'TICK'")
        # ลบ CFD trades ที่ resolve ผิด (hold_bars=0)
        conn2.execute("DELETE FROM cfd_paper_trades WHERE hold_bars = 0 AND result != 'OPEN'")
        # ลบ CFD trades ที่ signal resolve แล้วแต่ CFD ยัง OPEN
        conn2.execute(
            """DELETE FROM cfd_paper_trades
               WHERE result = 'OPEN' AND signal_id IN (
                   SELECT id FROM setup_signals WHERE result IN ('WIN','LOSE','DRAW')
               )"""
        )
        # ลบ CFD trades OPEN ที่เก่าเกิน 1 ชั่วโมง
        from datetime import datetime, timedelta, timezone

        stale_cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn2.execute(
            "DELETE FROM cfd_paper_trades WHERE result = 'OPEN' AND entry_time < ?", (stale_cutoff,)
        )
        conn2.commit()
        total_cleaned = (bad_tj or 0) + (bad_tj2 or 0) + (bad_trades or 0) + (tick_count or 0)
        if total_cleaned:
            print(f"[DB] Migration: ลบ {total_cleaned} รายการที่เกี่ยวกับ TICK ออกหมดแล้ว")
        print("[DB] Migration: cleaned all stale data")
        conn2.close()
    except Exception:
        pass
    try:
        _backfill_cfd_paper_trades()
    except Exception:
        pass
