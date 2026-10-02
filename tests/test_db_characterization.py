"""Characterization tests — backend/db (ก่อน/หลังแยกเป็น backend/db/ package)

ล็อกพฤติกรรมระดับฟังก์ชันของทุกโดเมน กับ SQLite ชั่วคราว — ห้ามแตะ data/bot.db จริง
(ดูกลไก patch DB_PATH ใน tests/conftest.py)
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

import backend.db as db

SIG_TIME = "2026-01-01T00:00:00+00:00"
TARGET_TIME = "2026-01-01T00:15:00+00:00"
ENTRY_PRICE = 2000.0

ALL_TABLES = {
    "setup_signals",
    "ml_signals",
    "ml_latest",
    "prices",
    "ticks",
    "macro_1h",
    "trade_journal",
    "cfd_paper_trades",
    "tick_touch_log",
    "model_registry",
    "daily_stats",
    "trading_config",
}


def _setup_signal_id(**over) -> int:
    kwargs = dict(
        signal_time=SIG_TIME,
        entry_price=ENTRY_PRICE,
        direction="CALL",
        confidence=0.6,
        horizon_min=15,
        target_time=TARGET_TIME,
    )
    kwargs.update(over)
    return db.insert_setup_signal(**kwargs)


def _ml_signal_id(**over) -> int:
    kwargs = dict(
        signal_time=SIG_TIME,
        entry_price=ENTRY_PRICE,
        direction="CALL",
        confidence=0.6,
        horizon_min=15,
        target_time=TARGET_TIME,
    )
    kwargs.update(over)
    return db.insert_ml_signal(**kwargs)


def _trade_id(signal_id, signal_type="SETUP", entry_time=SIG_TIME, **over) -> int:
    kwargs = dict(
        signal_id=signal_id,
        signal_type=signal_type,
        timeframe="M1",
        symbol="frxXAUUSD",
        direction="CALL",
        entry_price=ENTRY_PRICE,
        entry_time=entry_time,
        hold_min=15,
    )
    kwargs.update(over)
    return db.insert_trade(**kwargs)


def test_get_conn_uses_patched_temp_file(temp_db):
    """get_conn ต้องชี้ไฟล์ temp เท่านั้น + row_factory = sqlite3.Row"""
    conn = db.get_conn()
    db_list = conn.execute("PRAGMA database_list").fetchall()
    main_file = next(r[2] for r in db_list if r[1] == "main")
    assert main_file == str(temp_db)
    row = conn.execute("SELECT 1 AS one").fetchone()
    assert row["one"] == 1  # Row factory ตามเดิม (เข้าถึงด้วยชื่อคอลัมน์ได้)
    conn.close()


def test_init_db_creates_all_tables(temp_db):
    db.init_db()
    conn = db.get_conn()
    names = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    conn.close()
    assert ALL_TABLES <= names


def test_setup_signal_full_roundtrip(temp_db):
    sid = _setup_signal_id(score=11, total=15, tier="A")
    assert isinstance(sid, int) and sid > 0

    pending = db.fetch_pending_setup_signals(symbol="frxXAUUSD")
    assert [r["id"] for r in pending] == [sid]
    assert pending[0]["result"] == "PENDING"
    assert db.fetch_pending_setup_signals(symbol="frxEURUSD") == []
    assert sid in [r["id"] for r in db.fetch_pending_setup_signals()]

    assert [r["id"] for r in db.fetch_recent_setup_signals(limit=10, exclude_tick=True)] == [sid]
    assert db.fetch_recent_setup_signals(symbol="frxEURUSD") == []

    last = db.fetch_last_setup_signal(timeframe="M1", symbol="frxXAUUSD")
    assert last["id"] == sid
    assert db.fetch_last_setup_signal(timeframe="M5", symbol="frxXAUUSD") is None

    assert db.count_setup_signals_since("2025-12-31T00:00:00+00:00") == 1
    assert db.count_setup_signals_since("2026-01-02T00:00:00+00:00") == 0

    db.update_setup_signal_result(sid, exit_price=2010.0, result="WIN")
    stats = db.compute_setup_stats(payout=0.82)
    assert stats["wins"] == 1 and stats["n_resolved"] == 1
    assert stats["winrate"] == 100.0 and stats["n_pending"] == 0
    for key in ("losses", "draws", "ci_low", "ci_high", "breakeven", "margin", "payout"):
        assert key in stats

    by_tf = db.compute_setup_stats_by_timeframe(payout=0.82)
    assert set(by_tf) == {"M1"}
    assert by_tf["M1"]["wins"] == 1


def test_ml_signal_roundtrip_and_ml_latest(temp_db):
    feats = {"ema_dist": 0.5}
    mid = _ml_signal_id(
        prob_up=0.62,
        prob_down=0.38,
        threshold_used=0.57,
        model_version="v2_meanrev",
        features=feats,
    )
    assert isinstance(mid, int) and mid > 0

    pending = db.fetch_pending_ml_signals()
    assert [r["id"] for r in pending] == [mid]
    assert json.loads(pending[0]["features_json"]) == feats

    db.update_ml_signal_result(mid, 2005.0, "LOSE")
    recent = db.fetch_recent_ml_signals(limit=5)
    assert recent[0]["result"] == "LOSE" and recent[0]["exit_price"] == 2005.0
    assert db.count_ml_signals_since("2025-12-31T00:00:00+00:00") == 1
    stats = db.compute_ml_stats()
    assert stats["losses"] == 1 and stats["n_resolved"] == 1
    assert set(db.compute_ml_stats_by_timeframe()) == {"M1"}

    db.upsert_ml_latest("M1", SIG_TIME, 0.62, 0.38, "CALL", 0.62, 0.57)
    latest = db.fetch_ml_latest()
    assert set(latest) == {"M1"}
    row = latest["M1"]
    assert row["prob_up"] == 0.62 and row["signal"] == "CALL"
    assert row["threshold_used"] == 0.57 and row["ts"] == SIG_TIME
    # upsert ซ้ำ = ทับค่าเดิม (ไม่เพิ่มแถว)
    db.upsert_ml_latest("M1", SIG_TIME, 0.7, 0.3, "CALL", 0.7, 0.6)
    assert db.fetch_ml_latest()["M1"]["prob_up"] == 0.7


def test_prices_and_ticks_roundtrip(temp_db):
    db.insert_price("2026-01-01T00:00:00+00:00", 2000.0, 2001.0, 1999.0, 2000.5)
    db.insert_price("2026-01-01T00:01:00+00:00", 2000.5, 2002.0, 2000.0, 2001.0, symbol="frxXAUUSD")
    rows = db.fetch_recent_prices(limit=10, symbol="frxXAUUSD")
    assert [r["ts"] for r in rows] == [  # เก่า → ใหม่ (reversed แล้ว)
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:01:00+00:00",
    ]
    assert rows[-1]["close"] == 2001.0
    assert rows[0]["symbol"] == "frxXAUUSD"  # DEFAULT_SYMBOL ใช้เมื่อไม่ระบุ

    last = db.fetch_last_prices(["frxXAUUSD", "frxEURUSD"], per_symbol=2)
    assert set(last) == {"frxXAUUSD", "frxEURUSD"}
    assert last["frxXAUUSD"][0]["c"] == 2001.0  # ใหม่ก่อนเก่า
    assert last["frxEURUSD"] == []

    candles = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-01-02T00:00:00+00:00")]),
    )
    assert db.backfill_prices(candles, symbol="frxXAUUSD") == 1
    assert db.backfill_prices(None) == 0  # ไม่มีข้อมูล → ไม่เขียนอะไร

    db.insert_tick("2026-01-01T00:00:01+00:00", 2001.25)
    db.insert_tick("2026-01-01T00:00:02+00:00", 2001.5)
    conn = db.get_conn()
    assert conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0] == 2
    conn.close()


def test_trades_journal_and_daily_stats(temp_db):
    sid = _setup_signal_id()
    tid = _trade_id(sid, payout=0.82)
    assert isinstance(tid, int) and tid > 0

    rows = db.fetch_recent_trades(limit=10)
    assert [r["id"] for r in rows] == [tid]
    assert rows[0]["result"] == "PENDING"
    assert db.fetch_recent_trades(signal_type="ML") == []

    db.update_trade_result(
        tid, exit_price=2010.0, exit_time="2026-01-01T00:15:00+00:00", result="WIN"
    )
    row = db.fetch_recent_trades()[0]
    assert row["result"] == "WIN" and row["pnl"] == 0.82
    assert row["win_amount"] == 0.82 and row["loss_amount"] == 0

    stats = db.compute_journal_stats(payout=0.82)
    assert stats["n"] == 1 and stats["wins"] == 1 and stats["losses"] == 0
    assert stats["total_pnl"] == 0.82
    for key in ("winrate", "ci_low", "ci_high", "breakeven", "equity", "daily"):
        assert key in stats
    assert stats["equity"][0] == {"t": "2026-01-01T00:15:00+00:00", "equity": 0.82}
    assert stats["daily"][0]["day"] == "2026-01-01"

    # update trade ที่ไม่มีอยู่ → เงียบๆ (ไม่ raise)
    db.update_trade_result(9999, 1.0, "x", "WIN")

    # ⚠️ ล็อกพฤติกรรมจริง (latent bug ที่ยังไม่แก้ — Phase B เป็น move-only):
    # schema กำหนด daily_stats PK = (day) เดี่ยว แต่ upsert_daily_stat ใช้
    # ON CONFLICT(day, signal_type) → SQLite ปฏิเสธตอน prepare statement เสมอ
    # (ไม่มี production caller เรียกฟังก์ชันนี้อยู่ — ถ้าจะแก้ schema/SQL ต้องขออนุญาตแยก)
    import sqlite3

    with pytest.raises(sqlite3.OperationalError, match="ON CONFLICT"):
        db.upsert_daily_stat("2026-01-01", "SETUP", n_trades=1, n_wins=1, pnl=0.82)


def test_cfd_paper_flow(temp_db):
    sid = _setup_signal_id()
    cid = db.insert_cfd_paper_trade(
        signal_id=sid,
        signal_type="SETUP",
        symbol="frxXAUUSD",
        direction="CALL",
        entry_price=ENTRY_PRICE,
        entry_time=SIG_TIME,
    )
    assert isinstance(cid, int) and cid > 0

    open_trades = db.fetch_open_cfd_trades()
    assert [t["id"] for t in open_trades] == [cid]
    t = open_trades[0]
    # CALL: effective_entry = entry + spread/2 (pip_size 1.0), SL/TP ห่าง 20/40/60 pips
    assert t["effective_entry"] == 2000.75
    assert t["sl_price"] == 1980.75
    assert t["tp1_price"] == 2040.75
    assert t["tp2_price"] == 2060.75

    # โดน TP1 ครั้งแรก → ตั้ง flag แต่ไม่ปิด (คืนว่าง)
    assert db.check_cfd_trades(2040.75, "2026-01-01T00:05:00+00:00", symbol="frxXAUUSD") == []
    conn = db.get_conn()
    assert (
        conn.execute("SELECT tp1_hit FROM cfd_paper_trades WHERE id=?", (cid,)).fetchone()[0] == 1
    )
    conn.close()

    # ราคาไปถึง TP2 → ปิดเป็น TP2
    resolved = db.check_cfd_trades(2061.0, "2026-01-01T00:10:00+00:00", symbol="frxXAUUSD")
    assert [r["id"] for r in resolved] == [cid]
    assert resolved[0]["result"] == "TP2"
    assert resolved[0]["hold_bars"] == 10  # นาทีนับจาก entry_time

    stats = db.fetch_cfd_stats()
    assert stats["total"] == 1 and stats["tp2"] == 1 and stats["open"] == 0
    for key in ("sl", "tp1", "wr", "total_pnl", "by_type", "by_direction", "trades", "open_trades"):
        assert key in stats

    # จำกัด 10 OPEN ต่อ symbol → ไม้ที่ 11 ถูกปฏิเสธ (คืน None)
    for i in range(10):
        assert (
            db.insert_cfd_paper_trade(
                signal_id=sid + i + 1,
                signal_type="SETUP",
                symbol="frxEURUSD",
                direction="CALL",
                entry_price=1.1,
                entry_time=SIG_TIME,
            )
            is not None
        )
    assert (
        db.insert_cfd_paper_trade(
            signal_id=sid + 99,
            signal_type="SETUP",
            symbol="frxEURUSD",
            direction="CALL",
            entry_price=1.1,
            entry_time=SIG_TIME,
        )
        is None
    )


def test_tick_touch_roundtrip(temp_db):
    lid = db.insert_tick_touch_log(
        signal_time=SIG_TIME,
        symbol="frxXAUUSD",
        touch_case="TICK_TOUCH",
        direction="CALL",
        entry_price=ENTRY_PRICE,
        ema200_price=1990.0,
        horizon_min=30,
        target_time="2026-01-01T00:30:00+00:00",
        conditions_json=json.dumps(
            {"c1": {"pass": True, "note": ""}, "c2": {"pass": False, "note": ""}}
        ),
        passed_count=1,
    )
    assert isinstance(lid, int) and lid > 0
    assert db.fetch_last_tick_touch("frxXAUUSD")["id"] == lid
    assert db.fetch_last_tick_touch("frxEURUSD") is None
    assert [r["id"] for r in db.fetch_pending_tick_touch("frxXAUUSD")] == [lid]

    db.update_tick_touch_result(lid, 2005.0, "WIN", "2026-01-01T00:30:00+00:00")
    stats = db.fetch_tick_touch_stats(limit_recent=10)
    assert stats["total"] == 1 and stats["resolved"] == 1 and stats["wins"] == 1
    assert stats["by_case"]["TICK_TOUCH"]["wr"] == 100.0
    assert stats["by_condition"]["c1"]["true_n"] == 1
    assert stats["by_condition"]["c2"]["false_n"] == 1
    assert stats["recent"][0]["id"] == lid
    for key in ("pending", "wr", "by_case", "by_condition", "recent"):
        assert key in stats


def test_macro_config_registry_and_wilson(temp_db):
    db.upsert_macro_dxy("2026-01-01T00:00:00+00:00", 104.1)
    db.upsert_macro_dxy("2026-01-01T01:00:00+00:00", 104.2)
    db.upsert_macro_dxy("2026-01-01T01:00:00+00:00", 104.3)  # upsert = ทับแถวเดิม
    rows = db.fetch_macro_dxy(limit=10)
    assert [r["dxy_close"] for r in rows] == [104.1, 104.3]  # เก่า → ใหม่
    assert db.fetch_latest_macro_dxy()["dxy_close"] == 104.3

    assert db.get_config("capital") is None
    db.set_config("capital", 5000)
    assert db.get_config("capital") == "5000"  # เก็บเป็น string ตามพฤติกรรมเดิม
    assert db.get_config("missing", "d") == "d"
    assert db.fetch_trading_settings() == {"capital": 5000.0, "stake": 100.0, "currency": "THB"}

    db.register_model(
        "M1",
        "v2_meanrev",
        "2026-01-01T00:00:00+00:00",
        5,
        n_rows=1000,
        auc_val=0.55,
        auc_test=0.54,
        chosen_conf=0.57,
        feature_set="v2",
        note="t",
    )
    reg = db.fetch_model_registry(limit=10)
    assert reg[0]["model_key"] == "M1" and reg[0]["version"] == "v2_meanrev"

    assert db.wilson_ci(0, 0) == (0.0, 0.0)
    lo, hi = db.wilson_ci(1, 2)
    assert 0.0 <= lo <= hi <= 100.0


def test_money_report(temp_db):
    s1 = _setup_signal_id()
    t1 = _trade_id(s1, signal_type="SETUP", payout=0.82)
    s2 = _ml_signal_id()
    t2 = _trade_id(s2, signal_type="ML", payout=0.82)
    db.update_trade_result(t1, 2010.0, "2026-01-05T00:00:00+00:00", "WIN")
    db.update_trade_result(t2, 1990.0, "2026-01-06T00:00:00+00:00", "LOSE")

    report = db.compute_money_report()
    for key in ("settings", "summary", "cfd_summary", "daily", "weekly", "monthly", "yearly"):
        assert key in report
    a = report["summary"]["ALL"]
    assert a["n"] == 2 and a["wins"] == 1 and a["losses"] == 1
    # win = +payout unit, lose = -1 unit → 0.82 - 1.0 = -0.18
    assert a["pnl_units"] == pytest.approx(-0.18, abs=1e-3)
    assert report["summary"]["SETUP"]["n"] == 1
    assert report["summary"]["ML"]["n"] == 1
    assert report["daily"][0]["ALL"]["n"] == 1

    # กรองช่วงที่ไม่มี trade → ว่างหมด
    empty = db.compute_money_report(start="2026-02-01", end="2026-02-28")
    assert empty["daily"] == []
    assert empty["summary"]["ALL"]["n"] == 0
