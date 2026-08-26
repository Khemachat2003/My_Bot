"""MT5 Forex Executor — ดึงสัญญาณ FIRE จาก VPS (setup engine) แล้วส่งออเดอร์ MT5
พร้อม SL/TP อัตโนมัติ (ตาม default: fractal M5 + R:R 2.0, เสี่ยง 0.5%/ไม้)

รันบน Windows เท่านั้น (MetaTrader5 python module รองรับ Windows อย่างเป็นทางการ)
- ต้องมี MT5 terminal ติดตั้ง + login บัญชี demo/csd แล้ว
- โหมด --dry-run ทดสอบได้โดยไม่ต้องมี MT5 (จะ print ออเดอร์ที่ควรส่ง)

ตั้งค่าใน .env (ฝั่ง Windows):
  MT5_VPS_API_URL=http://<vps-ip>:8000
  MT5_API_USER / MT5_API_PASS   (DASHBOARD_USER/PASS ของ VPS; ว่างได้ถ้า VPS ไม่ตั้ง auth)
  MT5_RISK_PCT=0.5  MT5_RR=2.0  MT5_POLL_SECONDS=30
"""
import argparse
import datetime as dt
import json
import math
import os
import sqlite3
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
STATE_DB = ROOT / "mt5_state.db"

VPS_API_URL = os.getenv("MT5_VPS_API_URL", "").rstrip("/")
API_USER = os.getenv("MT5_API_USER", "")
API_PASS = os.getenv("MT5_API_PASS", "")
POLL_SECONDS = int(os.getenv("MT5_POLL_SECONDS", "30"))
RISK_PCT = float(os.getenv("MT5_RISK_PCT", "0.5"))
RR = float(os.getenv("MT5_RR", "2.0"))
SL_ATR = float(os.getenv("MT5_SL_ATR", "1.5"))
SL_BUFFER_ATR = float(os.getenv("MT5_SL_BUFFER_ATR", "0.25"))
DAILY_MAX = int(os.getenv("MT5_DAILY_MAX", "20"))
MAX_AGE_MIN = int(os.getenv("MT5_MAX_AGE_MIN", "10"))
MAGIC = int(os.getenv("MT5_MAGIC", "88501"))
SLOT_TF = "M5"

# สัญลักษณ์ VPS (Deriv) -> สัญลักษณ์ MT5 (คู่ forex major เท่านั้น; ทองอยู่ฝั่ง binary)
FX_MAP = {
    "frxEURUSD": "EURUSD",
    "frxGBPUSD": "GBPUSD",
    "frxUSDJPY": "USDJPY",
    "frxAUDUSD": "AUDUSD",
    "frxUSDCAD": "USDCAD",
    "frxUSDCHF": "USDCHF",
    "frxNZDUSD": "NZDUSD",
}

mt5 = None


def _log(msg: str) -> None:
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── State (sqlite ท้องถิ่น Windows) ─────────────────────────────────────────
def state_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(STATE_DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS processed_signals (
            id INTEGER PRIMARY KEY,
            processed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS trades (
            ticket INTEGER PRIMARY KEY,
            signal_id INTEGER, symbol TEXT, direction TEXT,
            entry REAL, sl REAL, tp REAL, volume REAL,
            opened_at TEXT, closed_at TEXT, pnl REAL, result TEXT
        );
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    return conn


def _processed_set(conn) -> set[int]:
    return {r[0] for r in conn.execute("SELECT id FROM processed_signals")}


def _mark_processed(conn, sid: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO processed_signals(id, processed_at) VALUES(?, ?)",
        (sid, dt.datetime.now(dt.timezone.utc).isoformat()),
    )
    conn.commit()


def _daily_count(conn) -> tuple[str, int]:
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute("SELECT value FROM meta WHERE key='daily'").fetchone()
    if not row or row[0] != today:
        return today, 0
    crow = conn.execute("SELECT value FROM meta WHERE key='daily_cnt'").fetchone()
    return today, int(crow[0]) if crow else 0


def _bump_daily(conn, today: str) -> None:
    _, cnt = _daily_count(conn)
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('daily', ?)", (today,))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('daily_cnt', ?)",
                 (str(cnt + 1),))
    conn.commit()


# ── ดึงสัญญาณจาก VPS ────────────────────────────────────────────────────────
def fetch_signals(limit: int = 50) -> list[dict]:
    if not VPS_API_URL:
        raise SystemExit("ตั้ง MT5_VPS_API_URL ใน .env ก่อน (เช่น http://<vps-ip>:8000)")
    auth = (API_USER, API_PASS) if API_USER else None
    r = requests.get(f"{VPS_API_URL}/api/signals", params={"limit": limit},
                     auth=auth, timeout=20)
    r.raise_for_status()
    return r.json()


def parse_sig_time(s: str) -> dt.datetime:
    s = s.replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t


# ── SL/TP จาก fractal M5 + ATR (ไม่ต้องใช้ MT5 — ทดสอบได้) ───────────────────
def _atr(df: pd.DataFrame, period: int = 14) -> float:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().iloc[-1])


def _last_fractals(df: pd.DataFrame) -> tuple[list, list]:
    piv_lows, piv_highs = [], []
    n = len(df)
    for i in range(2, n - 2):
        win_h = df["high"].iloc[i - 2:i + 3]
        win_l = df["low"].iloc[i - 2:i + 3]
        if df["high"].iloc[i] == win_h.max():
            piv_highs.append((df.index[i], float(df["high"].iloc[i])))
        if df["low"].iloc[i] == win_l.min():
            piv_lows.append((df.index[i], float(df["low"].iloc[i])))
    return piv_lows, piv_highs


def compute_sl_tp(df: pd.DataFrame, direction: str, entry: float,
                  rr: float = RR, atr_mult: float = SL_ATR,
                  buffer_mult: float = SL_BUFFER_ATR) -> tuple[float, float] | None:
    if len(df) < 30:
        return None
    atr = _atr(df)
    piv_lows, piv_highs = _last_fractals(df)
    if direction == "BUY":
        cands = [p for p in piv_lows if p[1] < entry]
        if cands:
            sl = cands[-1][1] - buffer_mult * atr
        else:
            sl = entry - atr_mult * atr
        sl = min(sl, entry - 0.5 * atr)
        tp = entry + rr * (entry - sl)
    else:
        cands = [p for p in piv_highs if p[1] > entry]
        if cands:
            sl = cands[-1][1] + buffer_mult * atr
        else:
            sl = entry + atr_mult * atr
        sl = max(sl, entry + 0.5 * atr)
        tp = entry - rr * (sl - entry)
    return sl, tp


# ── Volume (lot) จากความเสี่ยงที่กำหนด ──────────────────────────────────────
def _quote_conv(symbol: str) -> float:
    if mt5 is None:
        return 1.0
    info = mt5.account_info()
    if info is None:
        return 1.0
    acct = info.currency
    quote = (mt5.symbol_info(symbol) or type("S", (), {"currency_profit": ""})).currency_profit
    if not quote or quote == acct:
        return 1.0
    rate = mt5.symbol_info(f"{quote}{acct}")
    if rate is not None:
        t = mt5.symbol_info_tick(f"{quote}{acct}")
        if t is not None and t.bid > 0:
            return t.bid
    rate = mt5.symbol_info(f"{acct}{quote}")
    if rate is not None:
        t = mt5.symbol_info_tick(f"{acct}{quote}")
        if t is not None and t.bid > 0:
            return 1.0 / t.bid
    return 1.0


def calc_volume(entry: float, sl: float, risk_money: float, symbol: str) -> float:
    dist = abs(entry - sl)
    if dist <= 0:
        return 0.0
    contract = 100000.0
    if mt5 is not None:
        si = mt5.symbol_info(symbol)
        if si is not None and si.trade_contract_size > 0:
            contract = si.trade_contract_size
    lots = risk_money / (dist * contract * _quote_conv(symbol))
    return lots


def _norm_price(p: float, si) -> float:
    return round(p, si.digits)


# ── วางออเดอร์ (ผ่าน MT5) ───────────────────────────────────────────────────
def place_order(symbol: str, direction: str, entry: float, sl: float, tp: float,
                volume: float, signal_id: int, dry: bool) -> int:
    if dry:
        _log(f"[DRY] {symbol} {direction} vol={volume:.2f} entry={entry:.5f} "
             f"SL={sl:.5f} TP={tp:.5f} (signal#{signal_id})")
        return -signal_id
    si = mt5.symbol_info(symbol)
    if si is None:
        raise RuntimeError(f"MT5 ไม่รู้จักสัญลักษณ์ {symbol}")
    if si.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
        raise RuntimeError(f"{symbol} ไม่อนุญาตให้เทรด (trade_mode={si.trade_mode})")
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"{symbol} ไม่มี tick (ตลาดปิด?)")
    price = tick.ask if direction == "BUY" else tick.bid
    step = si.volume_step
    lots = max(math.floor(volume / step) * step, 0)
    if lots < si.volume_min or lots > si.volume_max:
        raise RuntimeError(
            f"{symbol} volume {lots:.2f} เกินขอบเขต [{si.volume_min}, {si.volume_max}]")
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": _norm_price(sl, si),
        "tp": _norm_price(tp, si),
        "deviation": 10,
        "magic": MAGIC,
        "comment": f"setup#{signal_id}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(request)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        rc = res.retcode if res is not None else "None"
        raise RuntimeError(f"order_send fail retcode={rc} request={request}")
    return res.order


def reconcile_open(conn) -> None:
    if mt5 is None:
        return
    now = dt.datetime.now()
    window_start = now - dt.timedelta(days=2)
    open_tickets = {p.ticket for p in mt5.positions_get(magic=MAGIC) or []}
    row = conn.execute(
        "SELECT ticket, signal_id, symbol, direction, entry, sl, tp, volume, opened_at "
        "FROM trades WHERE result IS NULL").fetchall()
    for r in row:
        ticket = r[0]
        if ticket <= 0:
            conn.execute("UPDATE trades SET result='DRY' WHERE ticket=?", (ticket,))
            conn.commit()
            continue
        if ticket in open_tickets:
            continue
        try:
            deals = mt5.history_deals_get(position=ticket)
        except Exception:
            deals = None
        if not deals:
            deals = mt5.history_deals_get(window_start, now) or []
            deals = [d for d in deals if d.position_id == ticket and d.magic == MAGIC]
        pnl = float(sum(d.profit for d in deals)) if deals else 0.0
        result = "WIN" if pnl > 0 else ("LOSE" if pnl < 0 else "DRAW")
        _log(f"ปิดไม้ ticket={ticket} {r[2]} {r[3]} pnl={pnl:.2f} -> {result}")
        conn.execute(
            "UPDATE trades SET closed_at=?, pnl=?, result=? WHERE ticket=?",
            (dt.datetime.now(dt.timezone.utc).isoformat(), pnl, result, ticket),
        )
        conn.commit()


def save_trade(conn, ticket: int, sid: int, symbol: str, direction: str,
               entry: float, sl: float, tp: float, volume: float) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO trades(ticket, signal_id, symbol, direction, "
        "entry, sl, tp, volume, opened_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (ticket, sid, symbol, direction, entry, sl, tp, volume,
         dt.datetime.now(dt.timezone.utc).isoformat()),
    )
    conn.commit()


def market_open(symbol: str) -> bool:
    if mt5 is None:
        return True
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False
    if dt.datetime.now().weekday() >= 5:
        return False
    age = time.time() - tick.time
    return age < 600


def process_signals(conn, dry: bool) -> None:
    try:
        rows = fetch_signals()
    except Exception as e:
        _log(f"ดึงสัญญาณล้มเหลว: {e}")
        return
    done = _processed_set(conn)
    today, dcount = _daily_count(conn)
    now = dt.datetime.now(dt.timezone.utc)
    new_sigs = [s for s in rows
                if s.get("tier") == "FIRE"
                and s.get("symbol") in FX_MAP
                and s.get("id") not in done]
    new_sigs.sort(key=lambda s: s["id"])

    for s in new_sigs:
        symbol = FX_MAP[s["symbol"]]
        age = (now - parse_sig_time(s["signal_time"])).total_seconds() / 60.0
        if age > MAX_AGE_MIN:
            _mark_processed(conn, s["id"])
            _log(f"ข้าม signal#{s['id']} {symbol} — อายุ {age:.0f}m เกิน {MAX_AGE_MIN}m")
            continue
        direction = "BUY" if s["direction"] == "CALL" else "SELL"
        _mark_processed(conn, s["id"])

        if not market_open(symbol):
            _log(f"ข้าม {symbol} — ตลาดไม่เปิด")
            continue
        if not dry:
            open_pos = mt5.positions_get(symbol=symbol, magic=MAGIC)
            if open_pos:
                _log(f"ข้าม {symbol} — มี position ค้างอยู่แล้ว")
                continue
        if dcount >= DAILY_MAX:
            _log(f"ถึง daily cap {DAILY_MAX} แล้ว — ข้าม {symbol}")
            continue
        if not dry:
            info = mt5.account_info()
            risk_money = (info.balance if info else 1000) * RISK_PCT / 100.0
        else:
            risk_money = 1000 * RISK_PCT / 100.0
        _log(f"สัญญาณ signal#{s['id']} {s['symbol']} -> MT5 {symbol} {direction} "
             f"(score {s.get('score')})")

        try:
            if dry:
                entry = float(s["entry_price"])
            else:
                tick = mt5.symbol_info_tick(symbol)
                entry = tick.ask if direction == "BUY" else tick.bid
            if not dry:
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 1, 300)
                if rates is None or len(rates) < 30:
                    _log(f"ข้าม {symbol} — เทียน M5 ไม่พอ")
                    continue
                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s")
                df = df.set_index("time")
            else:
                df = _demo_rates(entry)
            sl_tp = compute_sl_tp(df, direction, entry)
            if sl_tp is None:
                _log(f"ข้าม {symbol} — คำนวณ SL/TP ไม่ได้")
                continue
            sl, tp = sl_tp
            volume = calc_volume(entry, sl, risk_money, symbol)
            if volume <= 0:
                _log(f"ข้าม {symbol} — volume <= 0 (SL แคบเกินไป)")
                continue
            ticket = place_order(symbol, direction, entry, sl, tp, volume,
                                 s["id"], dry)
            save_trade(conn, ticket, s["id"], symbol, direction,
                       entry, sl, tp, volume)
            dcount += 1
            _bump_daily(conn, today)
            _log(f"วางออเดอร์ {symbol} {direction} vol={volume:.2f} entry={entry:.5f} "
                 f"SL={sl:.5f} TP={tp:.5f} ticket={ticket}")
        except Exception as e:
            _log(f"error ส่ง {symbol}: {e}")


def _demo_rates(entry: float) -> pd.DataFrame:
    idx = pd.date_range(end=dt.datetime.now(), periods=300, freq="5min")
    import numpy as np
    rng = np.random.default_rng(7)
    noise = rng.normal(0, entry * 0.001, 300)
    walk = np.cumsum(noise * 0.05)
    close = entry + walk + noise * 0.3
    high = close + np.abs(rng.normal(0, entry * 0.0004, 300))
    low = close - np.abs(rng.normal(0, entry * 0.0004, 300))
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close},
                        index=idx)


def run_once(dry: bool) -> None:
    conn = state_conn()
    reconcile_open(conn)
    process_signals(conn, dry)
    conn.close()


def main() -> None:
    global mt5
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="ไม่ส่งออเดอร์จริง (print อย่างเดียว)")
    ap.add_argument("--once", action="store_true", help="รันรอบเดียวแล้วจบ")
    ap.add_argument("--vps-api", default=None, help="ล้นจาก MT5_VPS_API_URL ได้")
    args = ap.parse_args()
    if args.vps_api:
        global VPS_API_URL
        VPS_API_URL = args.vps_api.rstrip("/")

    if not args.dry_run:
        try:
            import MetaTrader5 as _mt5
            mt5 = _mt5
        except ImportError:
            raise SystemExit(
                "ไม่พบ MetaTrader5 module — ติดตั้งบน Windows: pip install MetaTrader5\n"
                "และต้องรัน MT5 terminal + login บัญชี demo ก่อน. (ทดสอบได้ด้วย --dry-run)")
        if not mt5.initialize():
            raise SystemExit(f"MT5 initialize ล้มเหลว: {mt5.last_error()} — "
                             "เปิด MT5 terminal + login ก่อนรัน")
        info = mt5.account_info()
        _log(f"เชื่อมต่อ MT5: {info.login} ({info.name}) balance={info.balance:.2f} "
             f"{info.currency} | server={info.server}")
        _log(f"เทรด {len(FX_MAP)} คู่ | เสี่ยง {RISK_PCT}%/ไม้ | R:R {RR} | "
             f"poll {POLL_SECONDS}s | magic={MAGIC}")

    _log(f"เริ่ม executor (dry_run={args.dry_run}) VPS={VPS_API_URL}")
    while True:
        try:
            run_once(args.dry_run)
        except Exception as e:
            _log(f"รอบผิดพลาด: {e}")
        if args.once:
            break
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
