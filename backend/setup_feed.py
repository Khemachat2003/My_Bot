"""
setup_feed.py — 🔵 System 1: Rule-Based Setup Engine (Sniper Reversion 9 Checklists)
===================================================================================
รันแยก process:  python -m backend.setup_feed   (หรือผ่าน run_live.py รวม 3 ระบบ)

หน้าที่:
  1. Poll ดึง Candles ย้อนหลัง (1m) จาก Deriv ทุก SETUP_POLL_SECONDS วินาที
     (ใช้ ticks_history แบบเดียวกับ ML Engine — ไม่พึ่ง WebSocket subscribe
     เพราะ app_id สาธารณะ 1089 ปฏิเสธ subscribe real-time)
     และสลับ symbol อัตโนมัติเป็นตัวสำรอง R_100 เมื่อตลาดทองจริงปิดเสาร์-อาทิตย์
  2. คำนวณ 9-Checklist ผ่าน setup_scorer.score_setup() ทุกแท่งใหม่ → บันทึกลง
     ตาราง setup_scores (setup_db.py) เพื่อโชว์สถานะสดบน Dashboard
  3. เมื่อ entry_trigger เปลี่ยนจาก False → True (สัญญาณใหม่จริงๆ ไม่ยิงซ้ำ)
     → บันทึกลงตาราง setup_signals (db.py) และยิง Telegram [RULE-BASED ALERT]
  4. เมื่อสัญญาณ PENDING ครบเวลาถือออเดอร์ (15 นาทีสำหรับ M1 / 30 นาทีสำหรับ M5)
     → ประเมินผล WIN/LOSE บันทึกลง DB และยิง Telegram [RESULT] [RULE-BASED]

⚠️ ระบบนี้แยกขาดจาก 🟢 ML Model Engine (notifier.py) โดยสมบูรณ์:
   ไม่ใช้ตาราง ml_signals, ไม่ import โมดูล ml_forecaster ใดๆ
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ป้องกัน print ภาษาไทย/emoji แล้ว crash เมื่อ console เป็น cp1252
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

import pandas as pd

from backend import db, setup_db
from backend.telegram import send_telegram
from backend.market_hours import choose_symbol, symbol_label
from backend.setup_scorer import score_setup

try:
    from backend.deriv_feed import fetch_candles_history, DEFAULT_SYMBOL
except ModuleNotFoundError:
    from backend.data_feed.deriv_feed import fetch_candles_history, DEFAULT_SYMBOL

SYMBOL = DEFAULT_SYMBOL
BUFFER_MAX = 5000
FETCH_HISTORY_COUNT = 3500
POLL_SECONDS = int(os.getenv("SETUP_POLL_SECONDS", "15"))

# Timeframe ที่รัน (label, hold_minutes, resample_minutes)
#   ตั้งผ่าน env SETUP_TIMEFRAMES เช่น "M5:30:5" หรือ "M1:15:1,M5:30:5" (คั่นด้วย ,)
#   default: M5 เท่านั้น (จาก backtest 122 วัน M5 = 59.3% กำไร | M1 = 48% ขาดทุน)
_DEFAULT_TF = [("M5", 30, 5)]
_tf_env = os.getenv("SETUP_TIMEFRAMES", "").strip()
if _tf_env:
    _parsed_tf = []
    for part in _tf_env.split(","):
        bits = [b.strip() for b in part.split(":")]
        if len(bits) == 3:
            try:
                _parsed_tf.append((bits[0], int(bits[1]), int(bits[2])))
            except ValueError:
                pass
    SETUP_TIMEFRAMES = _parsed_tf or _DEFAULT_TF
else:
    SETUP_TIMEFRAMES = _DEFAULT_TF

SETUP_MIN_BARS = 30

# 🚦 กันสัญญาณถี่เกิน (เทคนิคจริงออกออเดอร์ไม่ถี่ — ตั้งค่าได้ใน setup_config.json / env)
#   - cooldown: อย่างน้อยกี่นาทีระหว่างสัญญาณแต่ละตัวของ TF เดียวกัน
#   - daily cap: สูงสุดกี่ไม้/วัน/ทั้งหมด (0 = ไม่จำกัด)
def _int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default

try:
    import json as _json
    _cfg_path = Path(__file__).resolve().parent / "setup_config.json"
    _cfg = _json.loads(_cfg_path.read_text(encoding="utf-8"))
    COOLDOWN_MIN = int(_cfg.get("cooldown_minutes", 30))
    DAILY_CAP = int(_cfg.get("daily_cap", 0))
except Exception:
    COOLDOWN_MIN = _int_env("SETUP_COOLDOWN_MINUTES", 30)
    DAILY_CAP = _int_env("SETUP_DAILY_CAP", 0)
COOLDOWN_MIN = _int_env("SETUP_COOLDOWN_MINUTES", COOLDOWN_MIN)
DAILY_CAP = _int_env("SETUP_DAILY_CAP", DAILY_CAP)


class SetupFeedEngine:
    def __init__(self):
        db.init_db()
        setup_db.init_setup_db()

        self._last_entry_trigger: dict[str, bool] = {}
        self.last_price: float = 0.0
        self.symbol = choose_symbol()
        self._symbol_switch_notified = False
        self.buffer = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        self._last_processed_ts: pd.Timestamp | None = None

        self._seed_buffer()
        print(f"[SetupFeed] poll={POLL_SECONDS}s | symbol={self.symbol} | "
              f"buffer={len(self.buffer)} แท่ง")

    # ── การจัดการข้อมูล ──────────────────────────────────────────────────────

    def _seed_buffer(self):
        """เริ่ม buffer ใหม่จาก history ของ symbol ที่กำลังใช้ (reset เมื่อสลับ symbol)"""
        print(f"[SetupFeed] กำลังดึงข้อมูลย้อนหลัง {FETCH_HISTORY_COUNT} แท่ง (1m, {self.symbol})...")
        try:
            df_init = fetch_candles_history(symbol=self.symbol, granularity=60,
                                            count=FETCH_HISTORY_COUNT)
            if df_init.index.tz is None:
                df_init.index = df_init.index.tz_localize("UTC")
            self.buffer = df_init.tail(BUFFER_MAX).copy()
            if not self.buffer.empty:
                self.last_price = float(self.buffer["close"].iloc[-1])
                # backfill ราคาย้อนหลังลงตาราง prices ให้กราฟ Dashboard เต็มทันที
                # (ไม่ต้องรอ poll สะสมทีละแท่งหลายชั่วโมง)
                n = db.backfill_prices(self.buffer, symbol=self.symbol)
                print(f"[SetupFeed] Backfill ราคาย้อนหลัง {n} แท่งลง prices (กราฟ Dashboard)")
            print(f"[SetupFeed] Buffer พร้อมใช้งาน: {len(self.buffer)} แท่ง (1m, {self.symbol})")
        except Exception as e:
            print(f"[SetupFeed] WARNING: ดึง History ไม่สำเร็จ ({e}) — รอรอบถัดไป")
            self.buffer = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def _merge_candles(self, df: pd.DataFrame):
        """รวมแท่งใหม่จาก poll เข้ากับ buffer (อัปเดตแท่งที่กำลังก่อตัว, เพิ่มแท่งใหม่)"""
        if self.buffer.empty:
            self.buffer = df.copy()
        else:
            for ts, row in df.iterrows():
                if ts in self.buffer.index:
                    self.buffer.loc[ts, "high"] = max(self.buffer.loc[ts, "high"], row["high"])
                    self.buffer.loc[ts, "low"] = min(self.buffer.loc[ts, "low"], row["low"])
                    self.buffer.loc[ts, "close"] = row["close"]
                    self.buffer.loc[ts, "volume"] = row.get("volume", 0)
                else:
                    self.buffer.loc[ts] = row
        self.buffer = self.buffer.sort_index().iloc[-BUFFER_MAX:]

    def _poll_update(self, now: pd.Timestamp):
        """หนึ่งรอบ poll: สลับ symbol ถ้าตลาดเปลี่ยน → ดึงราคา → merge → ประเมินสัญญาณ"""
        # 1. เช็คว่าต้องสลับ symbol หรือไม่ (เสาร์-อาทิตย์ / ตลาดเปิดใหม่)
        new_symbol = choose_symbol(now)
        if new_symbol != self.symbol:
            self._notify_symbol_switch(self.symbol, new_symbol)
            self._seed_buffer()
            self._last_processed_ts = None
            return

        # 2. ดึงแท่งล่าสุด (count เล็กพอสำหรับ poll บ่อยๆ)
        try:
            df = fetch_candles_history(symbol=self.symbol, granularity=60, count=15)
        except Exception as e:
            print(f"[SetupFeed] Poll ไม่สำเร็จ ({e})")
            return
        if df is None or df.empty:
            print("[SetupFeed] ไม่มีข้อมูลจาก poll ข้ามรอบนี้")
            return
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

        self._merge_candles(df)
        if self.buffer.empty:
            return

        self.last_price = float(self.buffer["close"].iloc[-1])

        # 3. เก็บแท่งล่าสุดลง prices (สำหรับกราฟ Dashboard) + tick
        last = self.buffer.iloc[-1]
        db.insert_price(
            pd.Timestamp(last.name).isoformat(),
            float(last["open"]), float(last["high"]),
            float(last["low"]), float(last["close"]),
            symbol=self.symbol,
        )
        db.insert_tick(now.isoformat(), self.last_price)

        # 4. ถ้ามีแท่งใหม่จริงๆ (timestamp เปลี่ยน) → ประเมิน checklist + สรุปผลสัญญาณ
        last_ts = pd.Timestamp(self.buffer.index[-1])
        if self._last_processed_ts is None or last_ts != self._last_processed_ts:
            self._last_processed_ts = last_ts
            self._check_setup_scorer(now)
            self._resolve_pending_signals(now)

    def _notify_symbol_switch(self, old_symbol: str, new_symbol: str):
        self._symbol_switch_notified = True
        self.symbol = new_symbol
        msg = (
            f"🔄 [SYMBOL SWITCH] ระบบ Rule-Based สลับสัญลักษณ์อัตโนมัติ\n"
            f"จาก: {symbol_label(old_symbol)} → เป็น: {symbol_label(new_symbol)}\n"
            f"เหตุผล: ตลาดหลักปิดหรือไม่สามารถรับราคาได้ — ระบบยังทำงานต่อด้วยสัญลักษณ์สำรอง"
        )
        send_telegram(msg)

    # 🏁 ตรวจสัญญาณ PENDING ที่ครบเวลาถือออเดอร์ → ประเมิน WIN/LOSE
    def _resolve_pending_signals(self, now: pd.Timestamp):
        try:
            pending = db.fetch_pending_setup_signals()
            for row in pending:
                sig_time = pd.to_datetime(row["signal_time"])
                elapsed_min = (now - sig_time).total_seconds() / 60.0
                if elapsed_min < row["horizon_min"]:
                    continue

                exit_price = self.last_price
                entry_price = row["entry_price"]
                direction = row["direction"]
                if direction == "CALL":
                    res = "WIN" if exit_price > entry_price else "LOSE"
                else:
                    res = "WIN" if exit_price < entry_price else "LOSE"

                db.update_setup_signal_result(row["id"], exit_price, res)

                # mirror ลง trade_journal (เก็บ P&L จำลอง)
                trade_id = db.insert_trade(
                    signal_id=row["id"], signal_type="SETUP", timeframe=row["timeframe"],
                    symbol=self.symbol,
                    direction=direction, entry_price=entry_price,
                    entry_time=row["signal_time"], hold_min=row["horizon_min"],
                    confidence=row["confidence"],
                )
                db.update_trade_result(trade_id, exit_price, now.isoformat(), res)

                pips_diff = abs(exit_price - entry_price)
                result_icon = "🟢 WIN" if res == "WIN" else "🔴 LOSE"
                sym_text = symbol_label(self.symbol)
                msg = (
                    f"🏁 [RESULT] [RULE-BASED] | ID #{row['id']} | TF: {row['timeframe']}\n"
                    f"Symbol: {sym_text} | ทิศทาง: {direction} | ผลลัพธ์: {result_icon}\n"
                    f"Entry: {entry_price:.2f} ➔ Exit: {exit_price:.2f} "
                    f"({'+' if res == 'WIN' else '-'}{pips_diff:.2f})\n"
                    f"ระยะเวลาที่ถือ: {row['horizon_min']} นาที\n"
                    f"เวลาสรุปผล: {now.strftime('%H:%M:%S')} UTC"
                )
                send_telegram(msg)
                print(f"[SetupFeed] สรุปผล ID #{row['id']} → {res}")
        except Exception:
            print("[SetupFeed] Error ในการสรุปผล PENDING signals:")
            traceback.print_exc()

    # 🎯 ตรวจ 9 Checklist ต่อ timeframe → บันทึก setup_scores เสมอ, ยิงสัญญาณเมื่อ trigger ใหม่
    def _check_setup_scorer(self, now: pd.Timestamp):
        for tf_label, hold_min, minutes in SETUP_TIMEFRAMES:
            df_tf = self._resample(minutes)
            if len(df_tf) < SETUP_MIN_BARS:
                continue

            try:
                result = score_setup(df_tf, timeframe=tf_label, target_hold_minutes=hold_min)
                setup_db.insert_setup_score(now.isoformat(), result)
            except Exception:
                print(f"[SetupFeed] setup_scorer error ({tf_label}):")
                traceback.print_exc()
                continue

            was_triggered = self._last_entry_trigger.get(tf_label, False)
            if result.entry_trigger and not was_triggered:
                # 🚦 cooldown: ข้ามถ้ายังไม่ครบเวลาจากสัญญาณล่าสุดของ TF นี้ (อิง DB — กัน restart ยิงซ้ำ)
                last_sig = db.fetch_last_setup_signal(timeframe=tf_label)
                if last_sig:
                    last_time = pd.to_datetime(last_sig["signal_time"])
                    elapsed = (now - last_time).total_seconds() / 60.0
                    if elapsed < COOLDOWN_MIN:
                        print(f"[SetupFeed] ข้ามสัญญาณ [{tf_label}] — ยังอยู่ใน cooldown "
                              f"{elapsed:.0f}/{COOLDOWN_MIN} นาที (ID#{last_sig['id']})")
                        self._last_entry_trigger[tf_label] = result.entry_trigger
                        continue

                # 🚦 daily cap: ข้ามถ้าวันนี้ยิงเกิน cap แล้ว (นับตั้งแต่ 00:00 UTC)
                if DAILY_CAP > 0:
                    start_of_day = pd.Timestamp(
                        now.tz_localize(None) if now.tz is not None else now
                    ).normalize().isoformat()
                    day_count = db.count_setup_signals_since(start_iso=start_of_day)
                    if day_count >= DAILY_CAP:
                        print(f"[SetupFeed] ข้ามสัญญาณ [{tf_label}] — ถึง daily cap {DAILY_CAP} แล้ว")
                        self._last_entry_trigger[tf_label] = result.entry_trigger
                        continue

                target_time = (now + pd.Timedelta(minutes=hold_min)).isoformat()
                try:
                    new_sig_id = db.insert_setup_signal(
                        signal_time=now.isoformat(),
                        entry_price=self.last_price,
                        direction=result.direction,
                        confidence=round(result.score / float(result.max_score), 4),
                        horizon_min=hold_min,
                        target_time=target_time,
                        timeframe=tf_label,
                        score=result.score,
                        total=result.max_score,
                        tier=result.tier,
                    )
                    print(f"[SetupFeed] บันทึกสัญญาณ ID #{new_sig_id} [{tf_label}] ลง setup_signals "
                          f"(รอวัดผลในอีก {hold_min} นาที)")
                except Exception:
                    print("[SetupFeed] ไม่สามารถบันทึกสัญญาณลง DB ได้:")
                    traceback.print_exc()

                sym_text = symbol_label(self.symbol)
                if self.symbol != SYMBOL:
                    sym_text = f"{sym_text} (สำรอง — ตลาดทองปิด)"
                msg_trigger = (
                    f"🔵 [RULE-BASED ALERT]\n"
                    f"Symbol: {sym_text} | TF: {tf_label} | Tier: {result.tier}\n"
                    f"Direction: {result.direction} | Entry: {self.last_price:.2f}\n"
                    f"Score: {result.score}/{result.max_score} | Hold: {hold_min}m\n"
                    f"เหตุผล: {result.entry_trigger_note}\n"
                    f"เวลาเข้า: {now.strftime('%H:%M:%S')} UTC"
                )
                ok = send_telegram(msg_trigger)
                print(f"[SetupFeed] Telegram ALERT [{tf_label}] {'ส่งสำเร็จ' if ok else 'ส่งไม่สำเร็จ (ดู log ด้านบน)'}")

            self._last_entry_trigger[tf_label] = result.entry_trigger

    def _resample(self, minutes: int) -> pd.DataFrame:
        if minutes == 1:
            return self.buffer

        rule = f"{minutes}min"
        o = self.buffer["open"].resample(rule, closed="left", label="left", origin="epoch").first()
        h = self.buffer["high"].resample(rule, closed="left", label="left", origin="epoch").max()
        l = self.buffer["low"].resample(rule, closed="left", label="left", origin="epoch").min()
        c = self.buffer["close"].resample(rule, closed="left", label="left", origin="epoch").last()
        v = self.buffer["volume"].resample(rule, closed="left", label="left", origin="epoch").sum()

        out = pd.concat([o, h, l, c, v], axis=1)
        out.columns = ["open", "high", "low", "close", "volume"]
        return out.dropna()

    def run(self):
        print(f"[SetupFeed] 🔵 เริ่มต้นระบบ Rule-Based Setup Engine (polling {POLL_SECONDS}s, {self.symbol})...")

        now_ts = pd.Timestamp(datetime.now(timezone.utc))
        self._check_setup_scorer(now_ts)

        while True:
            try:
                now_ts = pd.Timestamp(datetime.now(timezone.utc))
                self._poll_update(now_ts)
            except KeyboardInterrupt:
                print("\n[SetupFeed] หยุดการทำงานของระบบเรียบร้อยแล้ว")
                break
            except Exception:
                print("[SetupFeed] Error ในรอบ poll:")
                traceback.print_exc()
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    engine = SetupFeedEngine()
    try:
        engine.run()
    except KeyboardInterrupt:
        print("\n[SetupFeed] ปิดโปรแกรม")
