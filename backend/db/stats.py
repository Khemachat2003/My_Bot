"""db.stats — สถิติ winrate กลาง (setup/ml ใช้ร่วมกัน) — ย้ายจาก db.py แบบ move-only"""

from __future__ import annotations

from backend.db.connection import get_conn


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    margin = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)
    lo = (center - margin) / denom
    hi = (center + margin) / denom
    return round(lo * 100, 2), round(hi * 100, 2)


_ALLOWED_TABLES = {"setup_signals", "ml_signals"}


def _compute_stats(table: str, payout: float = 0.82) -> dict:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"table ไม่ถูกต้อง: {table}")
    conn = get_conn()
    row = conn.execute(
        f"""SELECT
             COUNT(*) FILTER (WHERE result != 'PENDING' AND COALESCE(phantom, 0) = 0) AS n_resolved,
             COUNT(*) FILTER (WHERE result = 'WIN' AND COALESCE(phantom, 0) = 0) AS wins,
             COUNT(*) FILTER (WHERE result = 'LOSE' AND COALESCE(phantom, 0) = 0) AS losses,
             COUNT(*) FILTER (WHERE result = 'DRAW' AND COALESCE(phantom, 0) = 0) AS draws,
             COUNT(*) FILTER (WHERE result = 'PENDING') AS n_pending
           FROM {table}"""
    ).fetchone()
    conn.close()

    n = row["n_resolved"] or 0
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    draws = row["draws"] or 0
    decided = wins + losses
    winrate = round(100 * wins / decided, 2) if decided else 0.0
    ci_low, ci_high = wilson_ci(wins, decided)
    breakeven = round(1 / (1 + payout) * 100, 2)
    margin = round(ci_low - breakeven, 2)

    return {
        "n_resolved": n,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "n_pending": row["n_pending"] or 0,
        "winrate": winrate,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "breakeven": breakeven,
        "margin": margin,
        "payout": payout,
    }


def _compute_stats_by_timeframe(table: str, payout: float = 0.82) -> dict:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"table ไม่ถูกต้อง: {table}")
    conn = get_conn()
    rows = conn.execute(
        f"""SELECT
             COALESCE(timeframe, 'M1') AS tf,
             COUNT(*) FILTER (WHERE result != 'PENDING' AND COALESCE(phantom, 0) = 0) AS n_resolved,
             COUNT(*) FILTER (WHERE result = 'WIN' AND COALESCE(phantom, 0) = 0) AS wins,
             COUNT(*) FILTER (WHERE result = 'LOSE' AND COALESCE(phantom, 0) = 0) AS losses,
             COUNT(*) FILTER (WHERE result = 'DRAW' AND COALESCE(phantom, 0) = 0) AS draws,
             COUNT(*) FILTER (WHERE result = 'PENDING') AS n_pending
           FROM {table}
           GROUP BY tf"""
    ).fetchall()
    conn.close()

    breakeven = round(1 / (1 + payout) * 100, 2)
    out = {}
    for r in rows:
        n = r["n_resolved"] or 0
        wins = r["wins"] or 0
        losses = r["losses"] or 0
        draws = r["draws"] or 0
        decided = wins + losses
        winrate = round(100 * wins / decided, 2) if decided else 0.0
        ci_low, ci_high = wilson_ci(wins, decided)
        margin = round(ci_low - breakeven, 2)
        out[r["tf"]] = {
            "n_resolved": n,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "n_pending": r["n_pending"] or 0,
            "winrate": winrate,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "breakeven": breakeven,
            "margin": margin,
            "payout": payout,
        }
    return out
