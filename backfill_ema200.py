import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "bot.db"
CFG_PATH = ROOT / "backend" / "setup_config.json"


def load_cfg() -> dict:
    if CFG_PATH.exists():
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def tf_minutes(tf: str) -> int:
    digits = "".join(ch for ch in tf if ch.isdigit())
    return int(digits) if digits else 5


def resample_tf(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 1:
        return df
    rule = f"{minutes}min"
    o = df["open"].resample(rule, closed="left", label="left", origin="epoch").first()
    h = df["high"].resample(rule, closed="left", label="left", origin="epoch").max()
    l = df["low"].resample(rule, closed="left", label="left", origin="epoch").min()
    c = df["close"].resample(rule, closed="left", label="left", origin="epoch").last()
    out = pd.concat([o, h, l, c], axis=1)
    out.columns = ["open", "high", "low", "close"]
    return out.dropna()


def main(db_path: str) -> None:
    cfg = load_cfg()
    tol_near = float(cfg.get("ema200_near_tol_pct", 0.35))
    ema100_tol = float(cfg.get("ema100_tol_pct", 0.08))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(setup_signals)").fetchall()}
    for c in ("ema200_price", "dist200_pct", "near_ema200", "crossed_ema100"):
        if c not in cols:
            conn.execute(f"ALTER TABLE setup_signals ADD COLUMN {c} REAL")
    conn.commit()

    rows = conn.execute(
        "SELECT id, symbol, timeframe, signal_time, entry_price, direction "
        "FROM setup_signals WHERE dist200_pct IS NULL"
    ).fetchall()
    if not rows:
        print("ไม่มีแถวที่ต้อง backfill (ทุกแถวมี dist200_pct แล้ว)")
        return

    groups: dict[tuple[str, int], list[sqlite3.Row]] = {}
    for r in rows:
        groups.setdefault((r["symbol"], tf_minutes(r["timeframe"])), []).append(r)

    updated = 0
    skipped = 0
    for (symbol, minutes), sigs in groups.items():
        px = conn.execute(
            "SELECT ts, open, high, low, close FROM prices WHERE symbol = ?",
            (symbol,),
        ).fetchall()
        if not px:
            skipped += len(sigs)
            continue
        df = pd.DataFrame([dict(p) for p in px])
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
        df = df.sort_values("ts").set_index("ts")
        rt = resample_tf(df, minutes)
        if rt.empty:
            skipped += len(sigs)
            continue
        ema200 = rt["close"].ewm(span=200, adjust=False).mean()
        ema100 = rt["close"].ewm(span=100, adjust=False).mean()
        idx = rt.index

        for s in sigs:
            sig_ts = pd.to_datetime(s["signal_time"], utc=True).tz_localize(None)
            bar = sig_ts.floor(f"{minutes}min")
            pos = idx.searchsorted(bar)
            if pos >= len(idx) or idx[pos] != bar:
                skipped += 1
                continue
            e200 = float(ema200.iloc[pos])
            e100 = float(ema100.iloc[pos])
            if not e200 or e200 != e200:
                skipped += 1
                continue
            entry = float(s["entry_price"])
            dist = abs(entry - e200) / e200 * 100.0
            near = 1 if dist <= tol_near else 0
            if s["direction"] == "CALL":
                crossed = 1 if entry < e100 * (1 + ema100_tol / 100.0) else 0
            else:
                crossed = 1 if entry > e100 * (1 - ema100_tol / 100.0) else 0
            conn.execute(
                "UPDATE setup_signals SET ema200_price=?, dist200_pct=?, "
                "near_ema200=?, crossed_ema100=? WHERE id=?",
                (round(e200, 5), round(dist, 4), near, crossed, s["id"]),
            )
            updated += 1

    conn.commit()

    print(f"อัปเดต {updated} แถว | ข้าม {skipped} แถว (ไม่มีเทียน/bar ตรง)")

    band = conn.execute(
        "SELECT near_ema200, result, count(*) FROM setup_signals "
        "WHERE dist200_pct IS NOT NULL AND result != 'PENDING' "
        "GROUP BY near_ema200, result ORDER BY near_ema200"
    ).fetchall()
    for near, res, cnt in band:
        print(f"near_ema200={near} {res} -> {cnt}")

    detail = conn.execute(
        "SELECT "
        "  CASE WHEN dist200_pct<=0.10 THEN 'A. <=0.10%' "
        "       WHEN dist200_pct<=0.35 THEN 'B. 0.10-0.35%' "
        "       WHEN dist200_pct<=1.00 THEN 'C. 0.35-1.00%' "
        "       ELSE 'D. >1.00%' END band, "
        "  result, count(*) FROM setup_signals "
        "WHERE dist200_pct IS NOT NULL AND result != 'PENDING' "
        "GROUP BY 1, 2 ORDER BY 1"
    ).fetchall()
    for b, res, cnt in detail:
        print(f"{b} {res} -> {cnt}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH), help="path to bot.db")
    args = parser.parse_args()
    main(args.db)
