"""routes/market — ข้อมูลราคา/สัญลักษณ์: /api/symbol /api/symbols /api/candles
/api/watchlist /api/prices (ย้ายจาก backend/api.py แบบ move-only)"""

from __future__ import annotations

import json
import time

import pandas as pd
from fastapi import APIRouter, Depends, Query

from backend import db
from backend.api import ROOT_DIR, require_auth
from backend.market_hours import choose_symbol, symbol_label

router = APIRouter()

# ── TF → Deriv granularity (วินาที) ─────────────────────────────────────────
TF_GRANULARITY = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
}
_CANDLE_CACHE: dict = {}  # (symbol, tf) -> (fetch_ts, rows)
_CANDLE_CACHE_TTL = 30  # กันยิง Deriv API ถี่เกินเมื่อสลับ TF

# ── watchlist: ราคาล่าสุดทุก symbol ใน request เดียว (ลด load จาก 8 → 1) ──
_WATCHLIST_SYMBOLS = (
    "frxXAUUSD",
    "frxEURUSD",
    "frxGBPUSD",
    "frxUSDJPY",
    "frxAUDUSD",
    "frxUSDCAD",
    "frxUSDCHF",
    "frxNZDUSD",
)
_WATCHLIST_CACHE: dict = {}  # "sym1,sym2" -> (fetch_ts, rows)
_WATCHLIST_CACHE_TTL = 10  # วินาที
_WATCHLIST_LIVE_TTL = 60  # symbol ที่ไม่มีใน DB ดึงสด แต่ไม่ถี่กว่านี้
_WATCHLIST_LIVE_MAX = 12  # สูงพอครอบทุก symbol — ปกติ feed ทำงานจะมีแค่ 1-2 ตัว
# (กันไว้ด้วย concurrency 3 + cache สองชั้น)
_WATCHLIST_LIVE_CACHE: dict = {}  # symbol -> (fetch_ts, (last, prev))
_WATCHLIST_STALE_SEC = 180  # ข้อมูลใน DB เก่ากว่านี้ = ไม่นับ (ไปดึงสดแทน)


def _ts_is_stale(ts) -> bool:
    """ts เก่า/ใช้ไม่ได้ → ต้องดึงสด (กันราคาค้างเป็นเดือน ๆ ใน watchlist)"""
    if not ts:
        return True
    try:
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() > _WATCHLIST_STALE_SEC
    except Exception:
        return True


def _live_last_prices(symbol: str):
    """(ราคาล่าสุด, ราคาก่อนหน้า) จาก Deriv สำหรับ symbol ที่ไม่ได้เก็บลง DB

    คืน (last, prev) — ต้องมีทั้งคู่ถึงจะคำนวณ % เปลี่ยนแปลงใน watchlist ได้
    cache 60 วิ เพื่อไม่ให้ยิง Deriv ถี่เกินไป (โดน rate-limit + VPS 1 vCPU หนัก)
    """
    hit = _WATCHLIST_LIVE_CACHE.get(symbol)
    now = time.time()
    if hit and now - hit[0] < _WATCHLIST_LIVE_TTL:
        return hit[1]
    pair = (None, None)
    try:
        from backend.data_feed.deriv_feed import fetch_candles_history

        df = fetch_candles_history(symbol=symbol, granularity=60, count=2)
        if df is not None and len(df):
            last = float(df["close"].iloc[-1])
            prev = float(df["close"].iloc[-2]) if len(df) >= 2 else None
            pair = (last, prev)
    except Exception:
        pair = (None, None)
    _WATCHLIST_LIVE_CACHE[symbol] = (now, pair)
    return pair


def _fetch_candles(symbol: str, tf: str, count: int) -> list[dict]:
    """ดึงแท่งเทียน history ตาม TF — cache 30 วิ + fallback resample จาก DB"""
    key = (symbol, tf)
    now = time.time()
    cached = _CANDLE_CACHE.get(key)
    # ใช้แคชได้เฉพาะเมื่อมีแท่ง >= ที่ขอ — กันเคส watchlist ยิง count=2 ก่อน
    # แล้วกราฟหลัก (count=300) โดนแคช 2 แท่งภายใน TTL 30 วิ → กราฟว่าง
    if cached and now - cached[0] < _CANDLE_CACHE_TTL and len(cached[1]) >= count:
        return cached[1]

    rows: list[dict] = []
    try:
        from backend.data_feed.deriv_feed import fetch_candles_history

        gran = TF_GRANULARITY[tf]
        df = fetch_candles_history(symbol=symbol, granularity=gran, count=count)
        if df is not None and len(df):
            rows = [
                {
                    "t": pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                    "o": float(r["open"]),
                    "h": float(r["high"]),
                    "l": float(r["low"]),
                    "c": float(r["close"]),
                    "v": float(r.get("volume", 0) or 0),
                }
                for ts, r in df.iterrows()
            ]
    except Exception:
        pass

    if not rows:
        # fallback: resample 1m ที่สะสมใน DB ตาม TF — ต้องกัน crash เพราะ watchlist
        # ยิง 10 req/5 วิ ทำให้ Deriv ถูก rate-limit บ่อย ถ้า fallback พัง → 500 → ราคา watchlist ว่าง
        try:
            minute = TF_GRANULARITY.get(tf, 60) // 60
            prices = db.fetch_recent_prices(limit=1000, symbol=symbol)
            if prices:
                rows = _resample_from_prices(prices, minute)
                if count and len(rows) > count:
                    rows = rows[-count:]  # คืนตามจำนวนที่ขอจริง (ไม่ยัดทั้งก้อน)
        except Exception as e:
            print(
                f"[api] candles fallback fail ({symbol}, {tf}, count={count}): "
                f"{type(e).__name__}: {str(e)[:140]}"
            )
            rows = []

    if rows:
        _CANDLE_CACHE[key] = (now, rows)  # แคชเฉพาะผลสำเร็จ — กันผลว่าง/พังติดแคช 30 วิ
    return rows


def _resample_from_prices(prices: list[dict], minutes: int) -> list[dict]:
    """resample รายการราคา 1m → แท่งตาม TF (ใช้ fallback เมื่อ Deriv ดึงไม่ได้)"""
    import pandas as pd

    if not prices:
        return []
    df = pd.DataFrame(prices)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)  # กัน ts ผสม naive/aware → บังคับ UTC
    df = df.set_index("ts")[["open", "high", "low", "close"]].sort_index()
    rule = f"{minutes}min"
    # origin="start_day" (ไม่ใช้ "epoch") — bucket ตรงกันกับ epoch สำหรับ TF ทุกตัวที่ระบบใช้
    # (1m/5m/15m/30m/1h/4h ล้วนหาร 24h ลงตัว) แต่ไม่ชน edge case tz-aware + origin='epoch'
    o = df["open"].resample(rule, closed="left", label="left", origin="start_day").first()
    h = df["high"].resample(rule, closed="left", label="left", origin="start_day").max()
    low_o = df["low"].resample(rule, closed="left", label="left", origin="start_day").min()
    c = df["close"].resample(rule, closed="left", label="left", origin="start_day").last()
    out = pd.concat([o, h, low_o, c], axis=1).dropna()
    return [
        {
            "t": pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
            "o": float(r["open"]),
            "h": float(r["high"]),
            "l": float(r["low"]),
            "c": float(r["close"]),
            "v": 0,
        }
        for ts, r in out.iterrows()
    ]


_SYMBOLS_CACHE = {"ts": 0.0, "data": None}


@router.get("/api/symbol")
def get_symbol(_auth=Depends(require_auth)):
    """สัญลักษณ์ที่ระบบกำลังใช้อยู่จริง (สลับ R_100 อัตโนมัติเมื่อตลาดทองปิด)"""
    sym = choose_symbol()
    return {"symbol": sym, "label": symbol_label(sym)}


@router.get("/api/symbols")
def get_symbols(_auth=Depends(require_auth)):
    """รายการสินทรัพย์ที่รองรับ (forex major + ทอง/เงิน + synthetic) สำหรับ dropdown กราฟ"""
    if _SYMBOLS_CACHE["data"] and time.time() - _SYMBOLS_CACHE["ts"] < 60:
        return _SYMBOLS_CACHE["data"]
    try:
        data = json.loads((ROOT_DIR / "backend" / "symbols.json").read_text(encoding="utf-8"))
        lst = data.get("symbols", [])
    except Exception:
        lst = []
    _SYMBOLS_CACHE.update(ts=time.time(), data=lst)
    return lst


@router.get("/api/candles")
def get_candles(
    tf: str = Query("1m", pattern="^(1m|5m|15m|30m|1h|4h)$"),
    count: int = Query(300, ge=2, le=1000),
    symbol: str = Query("", description="เช่น frxXAUUSD / R_100 / frxEURUSD"),
    _auth=Depends(require_auth),
):
    """แท่งเทียน history ตาม TF สำหรับกราฟ (1m/5m/15m/30m/1h/4h) — cache 30 วิ"""
    sym = symbol or db.DEFAULT_SYMBOL
    return _fetch_candles(sym, tf, count)


@router.get("/api/watchlist")
def get_watchlist(
    symbols: str = Query("", description="คั่นด้วย comma — เว้นว่าง = 8 ตัวมาตรฐาน"),
    _auth=Depends(require_auth),
):
    """ราคาล่าสุดของทุก symbol ที่แสดงใน watchlist — request เดียวจบ (cache 10 วิ)

    เดิม frontend ยิง /api/candles ทีละ symbol (8 requests/รอบ) ทำให้ VPS 1 vCPU
    ค้างและ connection reset → watchlist ไม่ขึ้น ตอนนี้รวมเป็น query เดียว
    """
    now = time.time()
    syms = [s.strip() for s in (symbols or "").split(",") if s.strip()][:20]
    if not syms:
        syms = list(_WATCHLIST_SYMBOLS)
    cache_key = ",".join(syms)
    cache = _WATCHLIST_CACHE.get(cache_key)
    if cache and now - cache[0] < _WATCHLIST_CACHE_TTL:
        return cache[1]
    try:
        raw = db.fetch_last_prices(syms, per_symbol=2)
    except Exception:
        raw = {}
    out = []
    missing = []
    for sym in syms:
        rows = raw.get(sym) or []
        last = rows[0] if rows else None
        prev = rows[1] if len(rows) >= 2 else None
        # ข้อมูลใน DB ที่เก่ากว่า _WATCHLIST_STALE_SEC ถือว่าไม่มี (เช่น symbol
        # เคยอยู่ใน TRADE_SYMBOLS แล้วถูกเอาออก — ราคาค้างเป็นเดือน ๆ)
        if last and _ts_is_stale(last.get("ts")):
            last, prev = None, None
        price = last["c"] if last else None
        chg = None
        if price is not None and prev and prev.get("c"):
            chg = (price - prev["c"]) / prev["c"] * 100
        if price is None:
            missing.append(sym)
        out.append(
            {"symbol": sym, "price": price, "chgPct": chg, "ts": last["ts"] if last else None}
        )
    # symbol ที่ไม่ได้อยู่ใน TRADE_SYMBOLS (เช่น XAGUSD / R_100) → ไม่มีในตาราง prices
    # ต้องดึงสดจาก Deriv แต่ไม่ให้ยิงทุก 5 วิ (โดน rate-limit + ทำให้ VPS หนัก)
    # → แคช 60 วิ แยกต่างหาก และจำกัดจำนวนไว้ไม่เกิน 4 ตัวต่อรอบ
    if missing:
        todo = missing[:_WATCHLIST_LIVE_MAX]
        try:
            from concurrent.futures import ThreadPoolExecutor

            # จำกัด 3 ตัวพร้อมกัน — ยิงพร้อมกันหลายตัว Deriv จะตอบ 429/ว่าง
            with ThreadPoolExecutor(max_workers=min(3, len(todo))) as pool:
                pairs = list(pool.map(_live_last_prices, todo))
            for sym, (last, prev) in zip(todo, pairs, strict=True):
                if last is None:
                    continue
                chg = (last - prev) / prev * 100 if prev else None
                for item in out:
                    if item["symbol"] == sym:
                        item["price"] = last
                        item["chgPct"] = chg
                        break
        except Exception:
            pass
    _WATCHLIST_CACHE[cache_key] = (now, out)
    return out


@router.get("/api/prices")
def get_prices(
    limit: int = Query(500, ge=1, le=5000),
    symbol: str = Query("", description="เช่น frxXAUUSD / R_100 — ว่าง = ค่าเริ่มต้น"),
    _auth=Depends(require_auth),
):
    """ราคา/กราฟ ใช้ร่วมกันทั้ง 2 ระบบ — กรองตาม symbol (กันสเกลราคาปนกัน)"""
    sym = symbol or db.DEFAULT_SYMBOL
    return db.fetch_recent_prices(limit=limit, symbol=sym)
