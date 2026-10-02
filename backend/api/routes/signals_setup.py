"""routes/signals_setup — สัญญาณ Rule-Based (🔵 System 1): /api/signals,
/api/signals/markers, /api/ticktouch/stats, /api/stats*, /api/setup/*
(ย้ายจาก backend/api.py แบบ move-only)"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from backend import db, setup_db
from backend.api import require_auth

router = APIRouter()


@router.get("/api/signals")
def get_signals(
    limit: int = Query(100, ge=1, le=1000),
    symbol: str | None = Query(None),
    _auth=Depends(require_auth),
):
    return db.fetch_recent_setup_signals(limit=limit, symbol=symbol, exclude_tick=True)


@router.get("/api/ticktouch/stats")
def get_tick_touch_stats(_auth=Depends(require_auth)):
    """สถิติ research แตะ EMA200 3 เคส + น้ำหนักโหวต checklist"""
    return db.fetch_tick_touch_stats()


@router.get("/api/signals/markers")
def get_signal_markers(
    symbol: str = Query("frxXAUUSD"),
    limit: int = Query(50, ge=1, le=200),
    _auth=Depends(require_auth),
):
    """ส่งสัญญาณทั้ง SETUP + ML + CFD สำหรับแสดง entry markers + levels บนกราฟ"""
    setup_rows = db.fetch_recent_setup_signals(limit=limit, symbol=symbol, exclude_tick=True)
    ml_rows = db.fetch_recent_ml_signals(limit=limit)

    # CFD trades: PENDING + resolved → map signal_id → cfd data
    conn = db.get_conn()
    cfd_rows = conn.execute(
        "SELECT signal_id, signal_type, direction, entry_price, effective_entry, "
        "sl_price, tp1_price, tp2_price, result, exit_price, pnl "
        "FROM cfd_paper_trades ORDER BY id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    cfd_map = {}
    for cr in cfd_rows:
        key = (cr["signal_type"], cr["signal_id"])
        if key not in cfd_map:
            cfd_map[key] = dict(cr)

    markers = []
    for r in setup_rows:
        m = {
            "type": "SETUP",
            "ts": r.get("signal_time"),
            "price": r.get("entry_price"),
            "direction": r.get("direction"),
            "result": r.get("result"),
            "importance": r.get("importance"),
            "touch_case": (json.loads(r.get("conditions_log_json") or "{}")).get("_touch_case", ""),
            "id": r.get("id"),
        }
        cfd = cfd_map.get(("SETUP", r.get("id")), {})
        if cfd:
            m["cfd"] = {
                "effective_entry": cfd.get("effective_entry"),
                "sl": cfd.get("sl_price"),
                "tp1": cfd.get("tp1_price"),
                "tp2": cfd.get("tp2_price"),
                "pnl": cfd.get("pnl"),
                "cfd_result": cfd.get("result"),
            }
        markers.append(m)
    for r in ml_rows:
        m = {
            "type": "ML",
            "ts": r.get("signal_time"),
            "price": r.get("entry_price"),
            "direction": r.get("direction"),
            "result": r.get("result"),
            "confidence": r.get("confidence"),
            "id": r.get("id"),
        }
        cfd = cfd_map.get(("ML", r.get("id")), {})
        if cfd:
            m["cfd"] = {
                "effective_entry": cfd.get("effective_entry"),
                "sl": cfd.get("sl_price"),
                "tp1": cfd.get("tp1_price"),
                "tp2": cfd.get("tp2_price"),
                "pnl": cfd.get("pnl"),
                "cfd_result": cfd.get("result"),
            }
        markers.append(m)
    markers.sort(key=lambda x: x.get("ts") or "", reverse=True)
    return markers[:limit]


@router.get("/api/stats")
def get_stats(payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)):
    return db.compute_setup_stats(payout=payout)


@router.get("/api/stats/by_timeframe")
def get_stats_by_timeframe(
    payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)
):
    """Winrate แยกตาม timeframe (M1/M5) แบบ real-time — {"M1": {...}, "M5": {...}}"""
    return db.compute_setup_stats_by_timeframe(payout=payout)


@router.get("/api/setup/latest")
def get_setup_latest(symbol: str = Query("frxXAUUSD"), _auth=Depends(require_auth)):
    """ผลล่าสุดของ setup_scorer checklist ต่อ timeframe ของสัญลักษณ์
    → {"M1": {...}, "M5": {...}}"""
    return setup_db.fetch_latest_setup_scores(symbol=symbol)


@router.get("/api/setup/latest-all")
def get_setup_latest_all(_auth=Depends(require_auth)):
    """ผลล่าสุดของ setup_scorer checklist ทุกสัญลักษณ์ × ทุก timeframe
    → {"frxXAUUSD": {"M5": {...}}, "frxEURUSD": {"M5": {...}}, ...}"""
    return setup_db.fetch_latest_setup_all_symbols()


@router.get("/api/setup/history")
def get_setup_history(
    timeframe: str = Query("M1", pattern="^(M1|M5)$"),
    limit: int = Query(50, ge=1, le=500),
    symbol: str = Query("frxXAUUSD"),
    _auth=Depends(require_auth),
):
    return setup_db.fetch_recent_setup_scores(timeframe, limit=limit, symbol=symbol)
