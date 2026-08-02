"""
deriv_feed.py — Phase 2A: Real-time Data Feed จาก Deriv WebSocket API (Fixed Version)
======================================================================
"""
from __future__ import annotations

import json
import time
import traceback
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import os

import pandas as pd
import websocket  # pip install websocket-client

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

# 🟢 แก้ไข URL หลักให้ถูกต้อง พร้อมระบุ app_id=1089
DERIV_WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# 🟢 ปรับ symbol ผ่าน .env ได้ (DERIV_SYMBOL=R_100 เช่น) โดยไม่ต้องแก้โค้ด
# หมายเหตุ: frxXAUUSD คือราคาทองจริง ตลาดปิดวันเสาร์-อาทิตย์ (และช่วงปิดตลาด Forex)
# ทำให้ subscribe ticks สด/active_symbols ไม่เจอสัญลักษณ์นี้ช่วงนั้น (แต่ ticks_history
# ย้อนหลังยังดึงได้ปกติเพราะเป็นข้อมูลที่บันทึกไว้แล้ว) ถ้าต้องการทดสอบระบบได้ 24/7
# ให้ลองสลับไปใช้ synthetic/OTC index ของ Deriv เอง เช่น R_100 (Volatility 100 Index)
# ซึ่งเทรดได้ตลอดเวลาไม่มีวันหยุด
DEFAULT_SYMBOL = os.getenv("DERIV_SYMBOL", "frxXAUUSD")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


# ─── 1. ดึงแท่งเทียนย้อนหลัง (historical candles) ────────────────────────────

def fetch_candles_history(
    symbol: str = DEFAULT_SYMBOL,
    granularity: int = 60,     # วินาทีต่อแท่ง: 60=1m, 300=5m, 900=15m
    count: int = 1000,
    timeout: int = 15,
) -> pd.DataFrame:
    req = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": count,
        "end": "latest",
        "start": 1,
        "style": "candles",
        "granularity": granularity,
    }

    ws = websocket.create_connection(DERIV_WS_URL, timeout=timeout)
    try:
        ws.send(json.dumps(req))
        raw = ws.recv()
    finally:
        ws.close()

    data = json.loads(raw)
    if data.get("error"):
        raise RuntimeError(f"Deriv API error: {data['error']}")
    if "candles" not in data:
        raise RuntimeError(f"ไม่พบ candles ใน response: {raw[:300]}")

    candles = data["candles"]
    df = pd.DataFrame(candles)
    df["datetime"] = pd.to_datetime(df["epoch"], unit="s", utc=True)
    df = df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close"})
    df["volume"] = 0.0
    df = df.set_index("datetime")[["open", "high", "low", "close", "volume"]].astype(float)

    cache_path = DATA_DIR / f"deriv_{symbol}_{granularity}s.csv"
    df.to_csv(cache_path)
    print(f"[DerivFeed] ดึง {len(df)} แท่ง ({symbol}, {granularity}s) → บันทึก {cache_path}")
    return df


# ─── 2. Live tick stream + auto-aggregate เป็นแท่งเทียน ──────────────────────

class DerivTickStream:
    def __init__(
        self,
        symbol: str = DEFAULT_SYMBOL,
        candle_seconds: int = 60,
        on_candle_close: Optional[Callable[[dict], None]] = None,
        on_tick: Optional[Callable[[float, float], None]] = None,
        fallback_symbol: Optional[str] = None,
        on_symbol_switch: Optional[Callable[[str, str], None]] = None,
    ):
        self.symbol = symbol
        self.candle_seconds = candle_seconds
        self.on_candle_close = on_candle_close
        self.on_tick = on_tick
        self.fallback_symbol = fallback_symbol
        self.on_symbol_switch = on_symbol_switch

        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        self._cur_candle: Optional[dict] = None
        self._cur_bucket: Optional[int] = None

        # สัญลักษณ์ที่กำลังใช้จริง (อาจเปลี่ยนเป็น fallback เมื่อตลาดหลักปิด)
        self._active_symbol = symbol
        self._switched = False
        self._last_tick_time: Optional[float] = None

    def _handle_tick(self, price: float, epoch: float):
        self._last_tick_time = time.time()
        bucket = int(epoch // self.candle_seconds) * self.candle_seconds

        if self._cur_bucket is None:
            self._cur_bucket = bucket
            self._cur_candle = {
                "epoch": bucket, "open": price, "high": price,
                "low": price, "close": price,
            }
        elif bucket == self._cur_bucket:
            c = self._cur_candle
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price
        else:
            closed = self._cur_candle
            if self.on_candle_close:
                try:
                    self.on_candle_close(closed)
                except Exception:
                    print("[DerivFeed] on_candle_close error:")
                    traceback.print_exc()
            self._cur_bucket = bucket
            self._cur_candle = {
                "epoch": bucket, "open": price, "high": price,
                "low": price, "close": price,
            }

        if self.on_tick:
            self.on_tick(price, epoch)

    def _rotate_symbol(self, reason: str):
        """สลับไปสัญลักษณ์สำรอง (ใช้ตอนตลาดหลักปิด/InvalidSymbol) แล้วแจ้ง callback"""
        if self._switched or not self.fallback_symbol:
            return False
        if self.fallback_symbol == self._active_symbol:
            print(f"[DerivFeed] fallback symbol ซ้ำกับ symbol ปัจจุบัน ({self.fallback_symbol}) — สลับไม่ได้")
            self._switched = True
            return False
        old = self._active_symbol
        self._active_symbol = self.fallback_symbol
        self._switched = True
        print(f"[DerivFeed] สลับ symbol: {old} → {self.fallback_symbol} (เหตุผล: {reason})")
        if self.on_symbol_switch:
            try:
                self.on_symbol_switch(old, self.fallback_symbol)
            except Exception:
                traceback.print_exc()
        return True

    def _run(self):
        backoff = 5
        while self._running:
            try:
                symbol = self._active_symbol
                print(f"[DerivFeed] กำลังเชื่อมต่อ... subscribe {symbol}")
                self._ws = websocket.create_connection(DERIV_WS_URL, timeout=15)
                self._ws.settimeout(25)

                # 🟢 ใช้ ticks_history + subscribe:1 แทน {"ticks": symbol} เฉยๆ
                # เหตุผล: บางบัญชี/ภูมิภาคของ Deriv จะ reject การ subscribe "ticks"
                # ตรงๆ สำหรับสัญลักษณ์ forex/commodity (frx*) ด้วย error InvalidSymbol
                # แม้ว่า ticks_history (ที่ใช้ดึงราคาย้อนหลังตอน seed buffer) จะใช้ได้ปกติ
                # การขอผ่าน ticks_history+subscribe:1 คือวิธีที่ Deriv เอกสารแนะนำ และ
                # ใช้สัญลักษณ์เดียวกับที่ fetch_candles_history() พิสูจน์แล้วว่าใช้ได้จริง
                sub_req = {
                    "ticks_history": symbol,
                    "adjust_start_time": 1,
                    "end": "latest",
                    "count": 1,
                    "style": "ticks",
                    "subscribe": 1,
                }
                self._ws.send(json.dumps(sub_req))

                print(f"[DerivFeed] เชื่อมต่อสำเร็จ ({symbol}) กำลังรอราคาสด...")
                backoff = 5
                self._connected_at = time.time()
                last_ping = time.time()
                invalid_symbol_count = 0

                while self._running:
                    # watchdog: ตลาดหลักปิด (ไม่มี tick มาเลย) → สลับไปตัวสำรอง
                    if (self._last_tick_time is None
                            and time.time() - self._connected_at > 120
                            and self.fallback_symbol
                            and not self._switched):
                        self._rotate_symbol(f"ไม่มี tick มาเลยเกิน 120 วิ (ตลาด {symbol} อาจปิด)")
                        # restart loop เพื่อ connect กับ symbol ใหม่
                        break

                    if time.time() - last_ping > 20:
                        self._ws.send(json.dumps({"ping": 1}))
                        last_ping = time.time()

                    try:
                        raw = self._ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue

                    data = json.loads(raw)

                    if data.get("error"):
                        err = data["error"]
                        print(f"[DerivFeed] Deriv ตอบ error: code={err.get('code')} "
                              f"message={err.get('message')}")
                        if err.get("code") == "InvalidSymbol":
                            invalid_symbol_count += 1
                            if self._rotate_symbol("InvalidSymbol"):
                                break
                            if invalid_symbol_count >= 3:
                                print(
                                    "[DerivFeed] สัญลักษณ์นี้อาจไม่รองรับการ subscribe "
                                    "real-time บน app_id/บัญชีนี้ — ลองรัน "
                                    "`python -m backend.check_symbols` เพื่อดูรายชื่อ "
                                    "สัญลักษณ์ที่ใช้งานได้จริงบนบัญชีนี้"
                                )
                        continue

                    # 🟢 ข้าม snapshot ประวัติแรก (มากับ ticks_history ตอน subscribe)
                    if data.get("msg_type") == "history":
                        continue

                    # 🟢 ตรวจสอบและดึง Tick ข้อมูล (มาทั้งจาก msg_type=tick และ history+subscribe)
                    if "tick" in data:
                        tick = data["tick"]
                        price = float(tick["quote"])
                        epoch = float(tick["epoch"])
                        self._handle_tick(price, epoch)

            except Exception as e:
                if self._running:
                    print(f"[DerivFeed] connection error: {e} — ลองใหม่ใน {backoff} วินาที")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)
            finally:
                try:
                    if self._ws:
                        self._ws.close()
                except Exception:
                    pass

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass