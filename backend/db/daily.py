"""db.daily — upsert_daily_stat (แยกจาก settings เพื่อความชัดเจน) — move-only"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.db.connection import get_conn


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
