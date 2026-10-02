"""routes/journal — Journal/P&L + model registry: /api/journal/* /api/models
(ย้ายจาก backend/api.py แบบ move-only)"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend import db
from backend.api import require_auth
from backend.api.schemas import JournalSettingsBody

router = APIRouter()


@router.get("/api/journal")
def get_journal(limit: int = Query(100, ge=1, le=1000), _auth=Depends(require_auth)):
    return db.fetch_recent_trades(limit=limit)


@router.get("/api/journal/stats")
def get_journal_stats(payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)):
    """P&L รวม + equity curve + daily breakdown จาก trade_journal"""
    return db.compute_journal_stats(payout=payout)


@router.get("/api/journal/settings")
def get_journal_settings(_auth=Depends(require_auth)):
    """ทุน / ขนาดไม้ / สกุลเงิน (ค่าใช้ในการคำนวณ P&L เป็นเงินจริง)"""
    return db.fetch_trading_settings()


@router.post("/api/journal/settings")
def set_journal_settings(body: JournalSettingsBody, _auth=Depends(require_auth)):
    if body.capital <= 0 or body.stake <= 0:
        raise HTTPException(status_code=400, detail="capital/stake ต้อง > 0")
    db.set_config("capital", body.capital)
    db.set_config("stake", body.stake)
    db.set_config("currency", (body.currency or "THB").strip().upper())
    return db.fetch_trading_settings()


@router.get("/api/journal/report")
def get_journal_report(_auth=Depends(require_auth)):
    """รายงาน P&L เป็นเงินจริง แยก ALL/ML/SETUP รายวัน/สัปดาห์/เดือน/ปี"""
    return db.compute_money_report()


@router.get("/api/journal/export")
def export_journal(
    start: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    _auth=Depends(require_auth),
):
    """ดาวน์โหลด Excel (.xlsx) — ประวัติเทรดทั้งหมด + สรุปแยกระบบ ทุกช่วงเวลา.
    ระบุ start/end ('YYYY-MM-DD') เพื่อกรองเฉพาะช่วง เช่น ?start=2026-08-01&end=2026-08-07"""
    report = db.compute_money_report(start=start, end=end)
    stake = report["settings"]["stake"]
    currency = report["settings"]["currency"]

    trades = db.fetch_recent_trades(limit=100000)
    if start or end:
        trades = [
            t
            for t in trades
            if (not start or (t.get("entry_time") or "")[:10] >= start)
            and (not end or (t.get("entry_time") or "")[:10] <= end)
        ]
    trades_df = pd.DataFrame(trades)
    if len(trades_df):
        trades_df = trades_df.sort_values("entry_time", ascending=False).reset_index(drop=True)
        trades_df["pnl_money"] = (trades_df["pnl"] * stake).round(2)
        trades_df["status"] = trades_df["result"]
        trades_df = trades_df.rename(
            columns={
                "signal_type": "ระบบ",
                "timeframe": "TF",
                "symbol": "สัญลักษณ์",
                "direction": "ทิศทาง",
                "entry_price": "ราคาเข้า",
                "exit_price": "ราคาออก",
                "entry_time": "เวลาเข้า",
                "exit_time": "เวลาออก",
                "hold_min": "ถือ(นาที)",
                "confidence": "confidence",
                "model_version": "โมเดล",
                "result": "ผล",
                "pnl": "P&L(หน่วย)",
                "payout": "payout",
                "note": "หมายเหตุ",
            }
        )
    else:
        trades_df = pd.DataFrame({"ระบบ": [], "TF": [], "ผล": [], "P&L(หน่วย)": [], "P&L(บาท)": []})

    def frame(rows, cols, labels):
        data = []
        for row in rows:
            rec = {"ช่วงเวลา": row["period"]}
            for s, name in (("ALL", "รวม"), ("ML", "ML"), ("SETUP", "Rule-Based")):
                a = row[s]
                rec[f"{name} เทรด"] = a["n"]
                rec[f"{name} ชนะ"] = a["wins"]
                rec[f"{name} Winrate%"] = a["winrate"] if a["n"] else ""
                rec[f"{name} P&L ({currency})"] = a["pnl_money"] if a["n"] else ""
                rec[f"{name} ROI%"] = a["roi"] if a["n"] else ""
            if row.get("balance") is not None:
                rec["ยอดคงเหลือ"] = row["balance"]
            data.append(rec)
        return pd.DataFrame(data, columns=cols + labels)

    labels = [
        f"{n} {c}"
        for n in ("รวม", "ML", "Rule-Based")
        for c in ("เทรด", "ชนะ", "Winrate%", f"P&L ({currency})", "ROI%")
    ]

    df_daily = frame(report["daily"], ["ช่วงเวลา"], labels)
    df_weekly = frame(report["weekly"], ["ช่วงเวลา"], labels)
    df_monthly = frame(report["monthly"], ["ช่วงเวลา"], labels)
    df_yearly = frame(report["yearly"], ["ช่วงเวลา"], labels)

    sum_rows = []
    for s, name in (("ALL", "รวม (ALL)"), ("ML", "ML"), ("SETUP", "Rule-Based")):
        a = report["summary"][s]
        sum_rows.append(
            {
                "ระบบ": name,
                "เทรด": a["n"],
                "ชนะ": a["wins"],
                "แพ้": a["losses"],
                "Winrate%": a["winrate"],
                "P&L (หน่วย)": a["pnl_units"],
                f"P&L ({currency})": a["pnl_money"],
                "ROI%": a["roi"],
            }
        )
    df_summary = pd.DataFrame(sum_rows)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_summary.to_excel(writer, sheet_name="สรุป", index=False)
        trades_df.to_excel(writer, sheet_name="ประวัติเทรด", index=False)
        df_daily.to_excel(writer, sheet_name="รายวัน", index=False)
        df_weekly.to_excel(writer, sheet_name="รายสัปดาห์", index=False)
        df_monthly.to_excel(writer, sheet_name="รายเดือน", index=False)
        df_yearly.to_excel(writer, sheet_name="รายปี", index=False)

    span = ""
    if start and end and start == end:
        span = f"_{start}"
    elif start or end:
        span = f"_{start or '0000'}__{end or '9999'}"
    fname = f"trading_report{span}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/api/models")
def get_models(_auth=Depends(require_auth)):
    """model registry — ดู version โมเดลที่เคยเทรนทั้งหมด"""
    return db.fetch_model_registry(limit=50)
