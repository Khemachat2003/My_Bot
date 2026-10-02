"""
db package — SQLite storage หลักของทั้งโปรเจกต์ (เดิม db.py ~1,621 บรรทัด)

🔵 System 1 (Rule-Based Setup Engine)  → ตาราง setup_signals
🟢 System 2 (ML Model Engine)          → ตาราง ml_signals + ml_latest
ราคา/กราฟ (ใช้ร่วมกันทั้ง 2 ระบบ)      → ตาราง prices / ticks

ห้าม insert/update ข้าม schema กัน — Rule-Based แตะเฉพาะ setup_* functions,
ML แตะเฉพาะ ml_* functions เท่านั้น เพื่อรักษา Decoupled Architecture ตาม spec

Phase B (move-only): แยกเป็น package แบบ re-export façade — **ห้ามเปลี่ยน
พฤติกรรม** · ทุก caller เดิม (from backend import db → db.<name>) ใช้งาน
เหมือนเดิมทุกชื่อ รวมตัวแปรและ helper ที่ถูกเรียกจาก engine (setup_feed/
notifier เรียก db.CFD_*, db._cfd_lot_size, db.DEFAULT_SYMBOL) — เลยแก้ไข
DB_PATH ใน module จริง: backend.db.connection (ดู tests/conftest.py)
"""

from __future__ import annotations

from backend.data_feed.deriv_feed import (
    DEFAULT_SYMBOL,  # noqa: F401 (caller เดิมใช้ db.DEFAULT_SYMBOL)
)
from backend.db.cfd import (  # noqa: F401
    CFD_CAPITAL,
    CFD_RISK_PCT,
    CFD_SL_PIPS,
    CFD_SPREAD_PIPS,
    CFD_TP1_PIPS,
    CFD_TP2_PIPS,
    _cfd_lot_size,
    check_cfd_trades,
    fetch_cfd_stats,
    fetch_open_cfd_trades,
    get_pip_size,
    get_pip_value,
    insert_cfd_paper_trade,
    update_cfd_result,
)
from backend.db.connection import (  # noqa: F401
    DB_PATH,
    MAX_PRICE_ROWS,
    MAX_TICK_ROWS,
    get_conn,
)
from backend.db.daily import (  # noqa: F401
    upsert_daily_stat,
)
from backend.db.macro import (  # noqa: F401
    fetch_latest_macro_dxy,
    fetch_macro_dxy,
    upsert_macro_dxy,
)
from backend.db.money import (  # noqa: F401
    compute_money_report,
)
from backend.db.prices import (  # noqa: F401
    backfill_prices,
    fetch_last_prices,
    fetch_recent_prices,
    insert_price,
    insert_tick,
)
from backend.db.registry import (  # noqa: F401
    fetch_model_registry,
    register_model,
)
from backend.db.schema import (  # noqa: F401
    init_db,
)
from backend.db.settings import (  # noqa: F401
    fetch_trading_settings,
    get_config,
    set_config,
)
from backend.db.signals_ml import (  # noqa: F401
    compute_ml_stats,
    compute_ml_stats_by_timeframe,
    count_ml_signals_since,
    fetch_ml_latest,
    fetch_pending_ml_signals,
    fetch_recent_ml_signals,
    insert_ml_signal,
    update_ml_signal_result,
    upsert_ml_latest,
)
from backend.db.signals_setup import (  # noqa: F401
    compute_setup_stats,
    compute_setup_stats_by_timeframe,
    count_setup_signals_since,
    fetch_last_setup_signal,
    fetch_pending_setup_signals,
    fetch_recent_setup_signals,
    insert_setup_signal,
    update_setup_signal_result,
)
from backend.db.stats import (  # noqa: F401
    _compute_stats,
    _compute_stats_by_timeframe,
    wilson_ci,
)
from backend.db.tick_touch import (  # noqa: F401
    fetch_last_tick_touch,
    fetch_pending_tick_touch,
    fetch_tick_touch_stats,
    insert_tick_touch_log,
    update_tick_touch_result,
)
from backend.db.trades import (  # noqa: F401
    compute_journal_stats,
    fetch_recent_trades,
    insert_trade,
    update_trade_result,
)


def main() -> None:
    init_db()


if __name__ == "__main__":
    main()
    print(f"[db] สร้าง/เช็คตารางเรียบร้อยที่ {DB_PATH}")
