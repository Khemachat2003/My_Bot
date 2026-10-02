"""db.settings — trading_config (ทุน/ขนาดไม้/สกุลเงิน) — ย้ายจาก db.py แบบ move-only"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.db.connection import get_conn

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
    return {"capital": float(capital), "stake": float(stake), "currency": currency or "THB"}


# ─── DAILY STATS (P&L curve) ─────────────────────────────────────────────────


def upsert_daily_stat(day: str, signal_type: str, n_trades: int, n_wins: int, pnl: float) -> None:
    conn = get_conn()
    winrate = round(100 * n_wins / n_trades, 2) if n_trades else 0.0
    conn.execute(
        """INSERT INTO daily_stats (day, signal_type, n_trades, n_wins, pnl, winrate, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(day, signal_type) DO UPDATE SET
             n_trades=excluded.n_trades, n_wins=excluded.n_wins,
             pnl=excluded.pnl, winrate=excluded.winrate, updated_at=excluded.updated_at""",
        (day, signal_type, n_trades, n_wins, pnl, winrate, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
