"""routes/cfd — CFD backtest/paper: /api/cfd/* (ย้ายจาก backend/api.py แบบ move-only)"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api import require_auth

router = APIRouter()


@router.get("/api/cfd/backtest")
def get_cfd_backtest(
    signal_type: str = Query("ALL", pattern="^(ALL|ML|SETUP)$"),
    capital: float = Query(5000, ge=100, le=100000),
    sl_pips: int = Query(20, ge=5, le=100),
    tp1_pips: int = Query(40, ge=10, le=200),
    tp2_pips: int = Query(60, ge=10, le=300),
    spread_pips: float = Query(1.5, ge=0, le=10),
    risk_pct: float = Query(0.01, ge=0.001, le=0.1),
    _auth=Depends(require_auth),
):
    """CFD Backtest — จำลองเทรด CFD ด้วย signal เก่า + price data"""
    from backend.cfd_backtest import CFDBacktest

    bt = CFDBacktest(
        capital=capital,
        sl_pips=sl_pips,
        tp1_pips=tp1_pips,
        tp2_pips=tp2_pips,
        spread_pips=spread_pips,
        risk_pct=risk_pct,
    )
    return bt.run(signal_type)


@router.get("/api/cfd/paper")
def get_cfd_paper(_auth=Depends(require_auth)):
    """CFD Paper Trading — สถิติ realtime + live P&L สำหรับ OPEN trades"""
    from backend.db import fetch_cfd_stats, get_conn, get_pip_value

    stats = fetch_cfd_stats()
    open_trades = stats.get("open_trades", [])
    if open_trades:
        conn = get_conn()
        for t in open_trades:
            row = conn.execute(
                "SELECT close FROM prices WHERE symbol = ? ORDER BY ts DESC LIMIT 1",
                (t.get("symbol", "frxXAUUSD"),),
            ).fetchone()
            if row:
                live_price = float(row[0])
                t["live_price"] = live_price
                ps = t["pip_size"]
                pv = get_pip_value(t.get("symbol", "frxXAUUSD"))
                if t["direction"] == "CALL":
                    t["unrealized_pips"] = round((live_price - t["effective_entry"]) / ps, 1)
                else:
                    t["unrealized_pips"] = round((t["effective_entry"] - live_price) / ps, 1)
                t["unrealized_pnl"] = round(t["unrealized_pips"] * pv * t["lot_size"], 2)
                t["dist_to_sl"] = round(abs(live_price - t["sl_price"]) / ps, 1)
                t["dist_to_tp1"] = round(abs(t["tp1_price"] - live_price) / ps, 1)
                t["dist_to_tp2"] = round(abs(t["tp2_price"] - live_price) / ps, 1)
        conn.close()
    return stats
