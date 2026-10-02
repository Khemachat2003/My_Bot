"""Money report (P&L เป็นเงินจริง) — ย้ายมาจาก backend/db.py เดิม (Phase B move-only)"""

from __future__ import annotations

from datetime import datetime

from backend.db.cfd import CFD_CAPITAL
from backend.db.connection import get_conn
from backend.db.settings import fetch_trading_settings

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
        recs.append(
            {
                "sys": d.get("signal_type") or "ML",
                "day": day,
                "week": week,
                "month": month,
                "year": year,
                "pnl": d.get("pnl") or 0,
                "win": 1 if d.get("result") == "WIN" else 0,
            }
        )

    def agg(sub) -> dict:
        n = len(sub)
        wins = sum(x["win"] for x in sub)
        units = sum(x["pnl"] for x in sub)
        return {
            "n": n,
            "wins": wins,
            "losses": n - wins,
            "winrate": round(100 * wins / n, 2) if n else 0.0,
            "pnl_units": round(units, 4),
            "pnl_money": round(units * stake, 2),
            "roi": round(100 * units * stake / capital, 2) if capital else 0.0,
        }

    # group recs by period
    by_period: dict[str, dict[str, list]] = {
        "day": {},
        "week": {},
        "month": {},
        "year": {},
    }
    for i, r in enumerate(recs):
        for kind, key in (
            ("day", r["day"]),
            ("week", r["week"]),
            ("month", r["month"]),
            ("year", r["year"]),
        ):
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

    # CFD summary (แยกจาก option)
    cfd_summary = {
        "n": 0,
        "wins": 0,
        "losses": 0,
        "winrate": 0.0,
        "pnl_money": 0.0,
        "capital": CFD_CAPITAL,
        "balance": CFD_CAPITAL,
    }
    try:
        conn2 = get_conn()
        cfd_rows = conn2.execute(
            "SELECT result, pnl FROM cfd_paper_trades WHERE result IN ('TP1','TP2','SL')"
        ).fetchall()
        conn2.close()
        if cfd_rows:
            cfd_n = len(cfd_rows)
            cfd_wins = sum(1 for r in cfd_rows if r["result"] in ("TP1", "TP2"))
            cfd_pnl = sum(r["pnl"] or 0 for r in cfd_rows)
            cfd_summary = {
                "n": cfd_n,
                "wins": cfd_wins,
                "losses": cfd_n - cfd_wins,
                "winrate": round(100 * cfd_wins / cfd_n, 2) if cfd_n else 0.0,
                "pnl_money": round(cfd_pnl, 2),
                "capital": CFD_CAPITAL,
                "balance": round(CFD_CAPITAL + cfd_pnl, 2),
            }
    except Exception:
        pass

    return {
        "settings": {"capital": capital, "stake": stake, "currency": currency},
        "summary": summary(),
        "cfd_summary": cfd_summary,
        "daily": build("day", lambda k: k),
        "weekly": build("week", lambda k: k),
        "monthly": build("month", lambda k: k),
        "yearly": build("year", lambda k: k),
    }
