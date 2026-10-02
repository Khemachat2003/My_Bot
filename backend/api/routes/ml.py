"""routes/ml — สัญญาณ ML (🟢 System 2): /api/ml/* (ย้ายจาก backend/api.py แบบ move-only)"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Query

from backend import db
from backend.api import require_auth

router = APIRouter()


@router.get("/api/ml/signals")
def get_ml_signals(limit: int = Query(100, ge=1, le=1000), _auth=Depends(require_auth)):
    return db.fetch_recent_ml_signals(limit=limit)


@router.get("/api/ml/stats")
def get_ml_stats(payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)):
    return db.compute_ml_stats(payout=payout)


@router.get("/api/ml/stats/by_timeframe")
def get_ml_stats_by_timeframe(
    payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)
):
    return db.compute_ml_stats_by_timeframe(payout=payout)


@router.get("/api/ml/latest")
def get_ml_latest(_auth=Depends(require_auth)):
    """ค่า prob_up/prob_down ล่าสุดต่อ timeframe → Real-time Probability Gauge"""
    data = db.fetch_ml_latest()
    # ส่ง threshold สดจาก .env ด้วย (เผื่อ DB ค้างค่าเก่า — user เปลี่ยน 0.57
    # แต่หน้าเว็บยังโชว์ 0.6 เพราะ ml_latest ยังเขียนด้วยค่าก่อน restart)
    env_conf = os.getenv("ML_CONF_THRESHOLD")
    env_threshold = None
    if env_conf and env_conf.strip():
        try:
            env_threshold = float(env_conf)
        except ValueError:
            pass
    if env_threshold is not None:
        for _k, v in data.items():
            v["env_threshold"] = env_threshold
    return data
