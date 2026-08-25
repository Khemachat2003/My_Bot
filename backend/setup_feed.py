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

import json
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
from backend.indicators import rsi
from backend.telegram import send_telegram
from backend.market_hours import is_forex_like, market_open_now, market_open_cooldown, symbol_label, get_session
from backend.setup_scorer import score_setup

try:
    from backend.deriv_feed import fetch_candles_history, DEFAULT_SYMBOL
except ModuleNotFoundError:
    from backend.data_feed.deriv_feed import fetch_candles_history, DEFAULT_SYMBOL

SYMBOL = DEFAULT_SYMBOL
BUFFER_MAX = 5000
FETCH_HISTORY_COUNT = 3500
POLL_SECONDS = int(os.getenv("SETUP_POLL_SECONDS", "15"))

# สัญลักษณ์ที่ระบบเทรดพร้อมกัน (คั่นด้วย ,) — default: ทอง + 7 คู่ major
# ตั้งใน .env เช่น: TRADE_SYMBOLS=frxXAUUSD,frxEURUSD,frxGBPUSD
_DEFAULT_TRADE_SYMBOLS = (
    "frxXAUUSD,frxEURUSD,frxGBPUSD,frxUSDJPY,"
    "frxAUDUSD,frxUSDCAD,frxUSDCHF,frxNZDUSD"
)
TRADE_SYMBOLS = [s.strip() for s in
                 os.getenv("TRADE_SYMBOLS", _DEFAULT_TRADE_SYMBOLS).split(",")
                 if s.strip()]

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

SETUP_MIN_BARS = 215

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
MARKET_OPEN_COOLDOWN_MIN = _int_env("SETUP_MARKET_OPEN_COOLDOWN_MINUTES", 15)


class SetupFeedEngine:
    def __init__(self, symbol: str = SYMBOL):
        db.init_db()
        setup_db.init_setup_db()

        self._last_entry_trigger: dict[str, bool] = {}
        self.last_price: float = 0.0
        self.symbol = symbol
        self.buffer = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        self._last_processed_ts: pd.Timestamp | None = None

        self._seed_buffer()
        print(f"[SetupFeed:{self.symbol}] poll={POLL_SECONDS}s | "
              f"buffer={len(self.buffer)} แท่ง")

    # ── การจัดการข้อมูล ──────────────────────────────────────────────────────

    def _seed_buffer(self):
        """เริ่ม buffer ใหม่จาก history ของ symbol นี้ (ดึงครั้งแรก/หลัง error)"""
        print(f"[SetupFeed:{self.symbol}] กำลังดึงข้อมูลย้อนหลัง {FETCH_HISTORY_COUNT} แท่ง (1m)...")
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
                print(f"[SetupFeed:{self.symbol}] Backfill ราคาย้อนหลัง {n} แท่งลง prices")
            print(f"[SetupFeed:{self.symbol}] Buffer พร้อมใช้งาน: {len(self.buffer)} แท่ง")
        except Exception as e:
            print(f"[SetupFeed:{self.symbol}] WARNING: ดึง History ไม่สำเร็จ ({e}) — รอรอบถัดไป")
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
        """หนึ่งรอบ poll ของ symbol นี้: ถ้าตลาดปิด → ข้ามดึงราคา (ยังสรุปผลสัญญาณค้าง)
        ถ้าตลาดเปิด → ดึงราคา → merge → ประเมินสัญญาณ"""

        # ตลาด forex/commodity ปิด (เสาร์-อาทิตย์ / ช่วงปิดรายวัน) → ข้าม poll
        # แต่ยังต้องสรุปผลสัญญาณ PENDING ที่ค้างจากช่วงตลาดเปิด (ใช้ราคาสุดท้าย)
        if is_forex_like(self.symbol) and not market_open_now(now):
            self._resolve_pending_signals(now)
            return

        # ดึงแท่งล่าสุด (count เล็กพอสำหรับ poll บ่อยๆ)
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

        # 4.5 🚨 TICK_TOUCH: ตรวจ real-time ว่าราคาแตะ EMA200 ณ ขณะนี้ (ไม่ต้องรอจบแท่ง)
        self._check_tick_touch(now)

        # 4. ถ้ามีแท่งใหม่จริงๆ (timestamp เปลี่ยน) → ประเมิน checklist + สรุปผลสัญญาณ
        last_ts = pd.Timestamp(self.buffer.index[-1])
        if self._last_processed_ts is None or last_ts != self._last_processed_ts:
            self._last_processed_ts = last_ts
            self._check_setup_scorer(now)
            self._resolve_pending_signals(now)

    def _check_tick_touch(self, now: pd.Timestamp):
        """ตรวจ real-time ว่าราคาปัจจุบันแตะ EMA200 หรือไม่
        ถ้าแตะ → FIRE Importance 1 ทันที (TICK_TOUCH)
        ป้องกันซ้ำ: ไม่ FIRE ถ้ามี signal เดียวกันภายใน 30 นาที
        """
        if len(self.buffer) < 210:
            return
        try:
            close = self.buffer["close"]
            ema200 = close.ewm(span=200, adjust=False).mean()
            e200 = float(ema200.iloc[-1])
            if e200 <= 0:
                return
            dist = abs(self.last_price - e200) / e200 * 100.0
            if dist > 0.01:
                return

            # ป้องกันซ้ำ: ดู signal ล่าสุดที่มี importance=1
            recent = db.fetch_recent_setup_signals(limit=1, symbol=self.symbol)
            if recent and recent[0].get("importance") == 1:
                sig_time = pd.to_datetime(recent[0]["signal_time"])
                if (now - sig_time).total_seconds() < 1800:
                    return

            if self.last_price >= e200:
                direction, bias = "CALL", "EMA200_TICK_BOUNCE"
            else:
                direction, bias = "PUT", "EMA200_TICK_BOUNCE"

            hold_min = 30
            target_time = (now + pd.Timedelta(minutes=hold_min)).isoformat()
            from backend.setup_scorer import score_setup
            result = score_setup(self.buffer, timeframe="TICK", target_hold_minutes=hold_min)
            new_sig_id = db.insert_setup_signal(
                signal_time=now.isoformat(),
                entry_price=self.last_price,
                direction=direction,
                confidence=1.0,
                horizon_min=hold_min,
                target_time=target_time,
                timeframe="TICK",
                score=0,
                total=0,
                tier="FIRE",
                symbol=self.symbol,
                ema200_price=e200,
                dist200_pct=round(dist, 4),
                near_ema200=True,
                crossed_ema100=False,
                importance=1,
                conditions_passed=result.conditions_passed,
                conditions_log_json=json.dumps(result.conditions_log, ensure_ascii=False, default=str),
            )
            db.insert_cfd_paper_trade(
                signal_id=new_sig_id, signal_type="SETUP",
                symbol=self.symbol, direction=direction,
                entry_price=self.last_price, entry_time=now.isoformat(),
            )
            ps = db.get_pip_size(self.symbol)
            spread = db.CFD_SPREAD_PIPS * ps
            eff = self.last_price + spread/2 if direction == "CALL" else self.last_price - spread/2
            if direction == "CALL":
                cfd_sl = eff - db.CFD_SL_PIPS * ps
                cfd_tp1 = eff + db.CFD_TP1_PIPS * ps
                cfd_tp2 = eff + db.CFD_TP2_PIPS * ps
            else:
                cfd_sl = eff + db.CFD_SL_PIPS * ps
                cfd_tp1 = eff - db.CFD_TP1_PIPS * ps
                cfd_tp2 = eff - db.CFD_TP2_PIPS * ps
            pv = db.get_pip_value(self.symbol)
            lot = db._cfd_lot_size(self.symbol)
            sym_text = symbol_label(self.symbol)
            msg = (
                f"⚡ [TICK TOUCH] Importance 1\n"
                f"Symbol: {sym_text} | ราคา {self.last_price:.5f} แตะ EMA200 ({e200:.5f})\n"
                f"Direction: {direction} | Hold: {hold_min}m\n"
                f"─── CFD Paper Trade ───\n"
                f"Entry (eff): {eff:.5f} | Lot: {lot}\n"
                f"SL: {cfd_sl:.5f} | TP1: {cfd_tp1:.5f} | TP2: {cfd_tp2:.5f}\n"
                f"Risk: ${db.CFD_CAPITAL * db.CFD_RISK_PCT:.0f} (1%)\n"
                f"TP1 Reward: ${db.CFD_TP1_PIPS * pv * lot:.2f}\n"
                f"TP2 Reward: ${db.CFD_TP2_PIPS * pv * lot:.2f}"
            )
            send_telegram(msg)
            print(f"[SetupFeed:{self.symbol}] 🚨 TICK_TOUCH → EMA200 = {e200:.5f}, "
                  f"price = {self.last_price:.5f}, dist = {dist:.4f}%")
        except Exception:
            pass

    # 🏁 ตรวจสัญญาณ PENDING ที่ครบเวลาถือออเดอร์ → ประเมิน WIN/LOSE
    def _resolve_pending_signals(self, now: pd.Timestamp):
        try:
            pending = db.fetch_pending_setup_signals(symbol=self.symbol)
            for row in pending:
                sig_time = pd.to_datetime(row["signal_time"])
                elapsed_min = (now - sig_time).total_seconds() / 60.0
                if elapsed_min < row["horizon_min"]:
                    continue

                exit_price = self.last_price
                entry_price = row["entry_price"]
                direction = row["direction"]
                if direction == "CALL":
                    res = "WIN" if exit_price > entry_price else (
                        "LOSE" if exit_price < entry_price else "DRAW")
                else:
                    res = "WIN" if exit_price < entry_price else (
                        "LOSE" if exit_price > entry_price else "DRAW")

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
                if res == "WIN":
                    result_icon = "🟢 WIN"
                elif res == "LOSE":
                    result_icon = "🔴 LOSE"
                else:
                    result_icon = "🟡 DRAW"
                sym_text = symbol_label(self.symbol)
                msg = (
                    f"🏁 [RESULT] [RULE-BASED] | ID #{row['id']} | TF: {row['timeframe']}\n"
                    f"Symbol: {sym_text} | ทิศทาง: {direction} | ผลลัพธ์: {result_icon}\n"
                    f"Entry: {entry_price:.5f} ➔ Exit: {exit_price:.5f} "
                    f"({'+' if res == 'WIN' else '-'}{pips_diff:.5f})\n"
                    f"ระยะเวลาที่ถือ: {row['horizon_min']} นาที\n"
                    f"เวลาสรุปผล: {now.strftime('%H:%M:%S')} UTC"
                )
                send_telegram(msg)
                print(f"[SetupFeed:{self.symbol}] สรุปผล ID #{row['id']} → {res}")
        except Exception:
            print(f"[SetupFeed:{self.symbol}] Error ในการสรุปผล PENDING signals:")
            traceback.print_exc()

        try:
            cfd_resolved = db.check_cfd_trades(self.last_price, now.isoformat(), symbol=self.symbol)
            for cr in cfd_resolved:
                icon = {"SL": "🔴", "TP1": "🟢", "TP2": "🟢"}.get(cr["result"], "❓")
                win_emoji = "WIN" if cr["result"] in ("TP1","TP2") else "LOSE"
                msg = (
                    f"📊 [CFD RESOLVED] {icon} {win_emoji}\n"
                    f"{cr['signal_type']} #{cr['signal_id']} | {cr['direction']}\n"
                    f"Entry (eff): {cr.get('effective_entry', cr['entry_price']):.2f}\n"
                    f"SL: {cr['sl_price']:.2f} | TP1: {cr['tp1_price']:.2f} | TP2: {cr['tp2_price']:.2f}\n"
                    f"Exit: {cr['exit_price']:.2f} | Result: {cr['result']}\n"
                    f"P&L: ${cr.get('pnl', 0):+.2f} | Hold: {cr['hold_bars']} bars"
                )
                send_telegram(msg)
                print(f"[SetupFeed:{self.symbol}] CFD #{cr['id']} → {cr['result']} P&L=${cr.get('pnl',0):+.2f}")
        except Exception:
            pass

    # 🛡️ Regime-Gate (shadow mode): คำนวณ gold 1h slope + DXY slope/RSI + agree
    # ตอนยิงสัญญาณ — ยังไม่บล็อก แค่บันทึกไว้วิเคราะห์ forward ว่า "เห็นพ้อง" ได้ winrate ≥60% จริง
    def _gate_features(self) -> tuple[float | None, float | None, float | None, int | None]:
        try:
            # gold 1h slope (24 ชม.) จาก buffer 1m
            g1 = self.buffer["close"].resample("1h", closed="left", label="left").last().dropna()
            if len(g1) < 26:
                return None, None, None, None
            gold_slope = (g1.iloc[-1] - g1.iloc[-25]) / g1.iloc[-25] * 100.0

            m = db.fetch_macro_dxy(limit=96)
            if len(m) < 26:
                return None, None, None, None
            dxy = pd.Series(
                [r["dxy_close"] for r in m],
                index=pd.to_datetime([r["ts"] for r in m], utc=True),
            ).dropna()
            dxy_slope = (dxy.iloc[-1] - dxy.iloc[-25]) / dxy.iloc[-25] * 100.0
            dxy_rsi_v = float(rsi(dxy, 14).iloc[-1])
            agree = int((gold_slope > 0) == (dxy_slope > 0))
            return (round(float(gold_slope), 4), round(float(dxy_slope), 4),
                    round(dxy_rsi_v, 2), agree)
        except Exception:
            return None, None, None, None

    # 🎯 ตรวจ 9 Checklist ต่อ timeframe → บันทึก setup_scores เสมอ, ยิงสัญญาณเมื่อ trigger ใหม่
    def _check_setup_scorer(self, now: pd.Timestamp):
        # 🛡️ กันสัญญาณผี: ราคาใน buffer ต้องสดพอ (ไม่ค้างจากช่วงตลาดปิด/feed freeze)
        # — แม้ market_hours พลาด (วันหยุดพิเศษ ฯลฯ) ก็ไม่ยิงจากข้อมูลเก่า
        if not self.buffer.empty:
            last_ts = pd.Timestamp(self.buffer.index[-1])
            age_min = (now - last_ts).total_seconds() / 60.0
            max_resample = max(m for _, _, m in SETUP_TIMEFRAMES)
            max_age_min = max_resample * 3 + 5
            if age_min > max_age_min:
                print(f"[SetupFeed:{self.symbol}] ข้ามประเมิน — ข้อมูลค้าง {age_min:.0f} นาที "
                      f"(เกิน {max_age_min}) ราคาสุดท้าย {last_ts} — รอ poll ราคาสด")
                return

        # 🚦 Market open cooldown: ข้าม FIRE信号ในช่วง N นาทีแรกหลังตลาดเปิดสัปดาห์
        #   กันสัญญาณถล่มตอน Monday open — spread กว้าง + whipsaw → LOSS ทุกไม้
        if is_forex_like(self.symbol) and market_open_cooldown(now, MARKET_OPEN_COOLDOWN_MIN):
            print(f"[SetupFeed:{self.symbol}] ข้ามประเมิน — market open cooldown "
                  f"({MARKET_OPEN_COOLDOWN_MIN} นาทีแรกหลังเปิดตลาดสัปดาห์)")
            return

        for tf_label, hold_min, minutes in SETUP_TIMEFRAMES:
            df_tf = self._resample(minutes)
            if len(df_tf) < SETUP_MIN_BARS:
                continue

            try:
                result = score_setup(df_tf, timeframe=tf_label, target_hold_minutes=hold_min)
                setup_db.insert_setup_score(now.isoformat(), result, symbol=self.symbol)
            except Exception:
                print(f"[SetupFeed:{self.symbol}] setup_scorer error ({tf_label}):")
                traceback.print_exc()
                continue

            was_triggered = self._last_entry_trigger.get(tf_label, False)
            if result.entry_trigger and not was_triggered:
                # 🚦 cooldown: ข้ามถ้ายังไม่ครบเวลาจากสัญญาณล่าสุดของ TF นี้ (อิง DB — กัน restart ยิงซ้ำ)
                last_sig = db.fetch_last_setup_signal(timeframe=tf_label, symbol=self.symbol)
                if last_sig:
                    last_time = pd.to_datetime(last_sig["signal_time"])
                    elapsed = (now - last_time).total_seconds() / 60.0
                    if elapsed < COOLDOWN_MIN:
                        print(f"[SetupFeed:{self.symbol}] ข้ามสัญญาณ [{tf_label}] — ยังอยู่ใน cooldown "
                              f"{elapsed:.0f}/{COOLDOWN_MIN} นาที (ID#{last_sig['id']})")
                        self._last_entry_trigger[tf_label] = result.entry_trigger
                        continue

                # 🚦 loss-streak cooldown: ข้ามถ้าสัญญาณล่าสุด 2 ไม้บน symbol นี้แพ้ทั้งคู่
                # → หยุด 4 ชม. (กันระบบยิงซ้ำ direction เดิมบน symbol ที่กำลังขาดทุน)
                recent = db.fetch_recent_setup_signals(limit=2, symbol=self.symbol)
                recent_resolved = [s for s in recent
                                   if s.get("result") in ("WIN", "LOSE") and not s.get("phantom")]
                if (len(recent_resolved) >= 2
                        and all(s["result"] == "LOSE" for s in recent_resolved)):
                    last_loss_time = pd.to_datetime(recent_resolved[0]["signal_time"])
                    loss_age_h = (now - last_loss_time).total_seconds() / 3600.0
                    if loss_age_h < 4.0:
                        print(f"[SetupFeed:{self.symbol}] ข้ามสัญญาณ [{tf_label}] — "
                              f"แพ้ 2 ไม้ติด หยุด 4 ชม. (เหลือ {4.0 - loss_age_h:.1f} ชม.)")
                        self._last_entry_trigger[tf_label] = result.entry_trigger
                        continue

                # 🚦 session throttle: Asia session (00-07 UTC) max 3/symbol (แทน daily cap 6)
                hour_utc = now.hour
                if 0 <= hour_utc < 7:
                    start_of_day = pd.Timestamp(
                        now.tz_localize(None) if now.tz is not None else now
                    ).normalize().isoformat()
                    asia_count = db.count_setup_signals_since(start_iso=start_of_day,
                                                             symbol=self.symbol)
                    if asia_count >= 3:
                        print(f"[SetupFeed:{self.symbol}] ข้ามสัญญาณ [{tf_label}] — "
                              f"Asia session cap (3/symbol) แล้ว ({asia_count} ไม้)")
                        self._last_entry_trigger[tf_label] = result.entry_trigger
                        continue

                # 🚦 daily cap: ข้ามถ้าวันนี้ยิงเกิน cap แล้ว (นับตั้งแต่ 00:00 UTC)
                if DAILY_CAP > 0:
                    start_of_day = pd.Timestamp(
                        now.tz_localize(None) if now.tz is not None else now
                    ).normalize().isoformat()
                    day_count = db.count_setup_signals_since(start_iso=start_of_day,
                                                             symbol=self.symbol)
                    if day_count >= DAILY_CAP:
                        print(f"[SetupFeed:{self.symbol}] ข้ามสัญญาณ [{tf_label}] — ถึง daily cap {DAILY_CAP} แล้ว")
                        self._last_entry_trigger[tf_label] = result.entry_trigger
                        continue

                # 🚦 session block: Night (18-24 UTC) = ตลาด volume ต่ำสุด — บล็อกทั้ง CALL/PUT
                # CALL Night: 34.1% WR (41 trades), PUT Night: 45.9% WR (37 trades)
                # ทั้งสองต่ำกว่า break-even 54.95% → ไม่เทรดช่วงนี้เลยดีกว่า
                if get_session(now) == "Night":
                    print(f"[SetupFeed:{self.symbol}] ข้ามสัญญาณ [{tf_label}] — "
                          f"Night session (volume ต่ำ, CALL 34% PUT 46%)")
                    self._last_entry_trigger[tf_label] = result.entry_trigger
                    continue

                target_time = (now + pd.Timedelta(minutes=hold_min)).isoformat()
                gold_slope, dxy_slope, dxy_rsi_v, gate_agree = self._gate_features()

                # 🚦 gate inversion: CALL + gate_agree=1 → 35.5% WR (กลับหัว)
                # ข้อมูล: gate_agree=1 CALL ชนะแค่ 11/31 = 35.5%
                # เมื่อ DXY "เห็นพ้อง" กับ CALL ทอง → มักจะเป็น false signal
                if (result.direction == "CALL" and gate_agree == 1):
                    print(f"[SetupFeed:{self.symbol}] ข้าม CALL [{tf_label}] — "
                          f"gate_agree=1 inverted (35.5% WR)")
                    self._last_entry_trigger[tf_label] = result.entry_trigger
                    continue

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
                        symbol=self.symbol,
                        ema200_price=result.ema200_price,
                        dist200_pct=result.dist200_pct,
                        near_ema200=result.near_ema200,
                        crossed_ema100=result.crossed_ema100,
                        gold_slope_1h=gold_slope,
                        dxy_slope_24=dxy_slope,
                        dxy_rsi=dxy_rsi_v,
                        gate_agree=gate_agree,
                        importance=result.importance,
                        conditions_passed=result.conditions_passed,
                        conditions_log_json=json.dumps({
                            "_touch_case": result.touch_case,
                            **result.conditions_log,
                        }, ensure_ascii=False, default=str),
                    )
                    print(f"[SetupFeed:{self.symbol}] บันทึกสัญญาณ ID #{new_sig_id} [{tf_label}] "
                          f"ลง setup_signals (รอวัดผลในอีก {hold_min} นาที)")
                    db.insert_cfd_paper_trade(
                        signal_id=new_sig_id, signal_type="SETUP",
                        symbol=self.symbol, direction=result.direction,
                        entry_price=self.last_price, entry_time=now.isoformat(),
                    )
                except Exception:
                    print(f"[SetupFeed:{self.symbol}] ไม่สามารถบันทึกสัญญาณลง DB ได้:")
                    traceback.print_exc()

                sym_text = symbol_label(self.symbol)
                gate_txt = "n/a"
                if gate_agree is not None:
                    gate_txt = ("เห็นพ้อง ✅" if gate_agree == 1 else "ขัดแย้ง ⛔")
                    gate_txt += f" (gold1h {gold_slope:+.2f}% | DXY24 {dxy_slope:+.2f}%)"
                passed_names = [k.replace("c","").replace("_"," ") 
                                for k, v in result.conditions_log.items() if v.get("pass")]
                checklist_txt = ", ".join(passed_names) if passed_names else "none"

                # แสดง checklist values ทั้งหมด (pass + fail)
                all_checks = []
                for k, v in result.conditions_log.items():
                    label = k.replace("c","").replace("_"," ")
                    val = "✅" if v.get("pass") else "❌"
                    note = (v.get("note") or "")[:40]
                    all_checks.append(f"{val} {label}: {note}")
                all_checks_txt = "\n".join(all_checks)

                touch_label = ""
                if result.touch_case:
                    touch_labels = {
                        "TICK_TOUCH": "⏱ TICK_TOUCH (ราคากดแตะ ณ ขณะนี้)",
                        "WICK_TOUCH": "📉 WICK_TOUCH (wick แตะ, แท่งปิดห่าง)",
                        "CLOSE_TOUCH": "📍 CLOSE_TOUCH (ปิดตรง EMA200)",
                    }
                    touch_label = touch_labels.get(result.touch_case, result.touch_case)

                imp_label = f"Importance {result.importance}" if result.importance else ""
                ps = db.get_pip_size(self.symbol)
                spread = db.CFD_SPREAD_PIPS * ps
                eff = self.last_price + spread/2 if result.direction == "CALL" else self.last_price - spread/2
                if result.direction == "CALL":
                    cfd_sl = eff - db.CFD_SL_PIPS * ps
                    cfd_tp1 = eff + db.CFD_TP1_PIPS * ps
                    cfd_tp2 = eff + db.CFD_TP2_PIPS * ps
                else:
                    cfd_sl = eff + db.CFD_SL_PIPS * ps
                    cfd_tp1 = eff - db.CFD_TP1_PIPS * ps
                    cfd_tp2 = eff - db.CFD_TP2_PIPS * ps
                pv = db.get_pip_value(self.symbol)
                lot = db._cfd_lot_size(self.symbol)
                msg_trigger = (
                    f"🔵 [RULE-BASED ALERT] {imp_label}\n"
                    f"Symbol: {sym_text} | TF: {tf_label} | Tier: {result.tier}\n"
                    f"Direction: {result.direction} | Entry: {self.last_price:.5f}\n"
                    f"EMA200: {result.ema200_price:.5f} | Dist: {result.dist200_pct:.3f}%\n"
                    f"Score: {result.score}/{result.max_score} | Hold: {hold_min}m\n"
                    f"{'-touch_case: ' + touch_label if touch_label else ''}\n"
                    f"Checklist ({result.conditions_passed}/10): {checklist_txt}\n"
                    f"Regime-Gate: {gate_txt}\n"
                    f"เหตุผล: {result.entry_trigger_note}\n"
                    f"เวลา: {now.strftime('%H:%M:%S')} UTC\n"
                    f"─── CFD Paper Trade ───\n"
                    f"Entry (eff): {eff:.5f} | Lot: {lot}\n"
                    f"SL: {cfd_sl:.5f} | TP1: {cfd_tp1:.5f} | TP2: {cfd_tp2:.5f}\n"
                    f"Risk: ${db.CFD_CAPITAL * db.CFD_RISK_PCT:.0f} (1%)\n"
                    f"TP1 Reward: ${db.CFD_TP1_PIPS * pv * lot:.2f}\n"
                    f"TP2 Reward: ${db.CFD_TP2_PIPS * pv * lot:.2f}\n"
                    f"─── รายการเงื่อนไข ───\n{all_checks_txt}"
                )
                ok = send_telegram(msg_trigger)
                print(f"[SetupFeed:{self.symbol}] Telegram ALERT [{tf_label}] "
                      f"{'ส่งสำเร็จ' if ok else 'ส่งไม่สำเร็จ (ดู log ด้านบน)'}")

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
        print(f"[SetupFeed:{self.symbol}] 🔵 เริ่ม Rule-Based Setup Engine "
              f"(polling {POLL_SECONDS}s) ...")

        now_ts = pd.Timestamp(datetime.now(timezone.utc))
        # 🐛 FIX (สัญญาณผีสุดสัปดาห์): ตอน restart ต้องไม่ประเมินสัญญาณทันทีถ้าตลาดปิด
        # (เดิมเรียก _check_setup_scorer ตรงๆ ไม่เช็ค market_open → ใช้ราคาค้างยิงสัญญาณผี)
        if is_forex_like(self.symbol) and not market_open_now(now_ts):
            print(f"[SetupFeed:{self.symbol}] ตลาดปิดตอน start — ข้ามประเมิน "
                  f"(จะเริ่มจริงเมื่อตลาดเปิด / poll ถัดไป)")
        else:
            self._check_setup_scorer(now_ts)

        while True:
            try:
                now_ts = pd.Timestamp(datetime.now(timezone.utc))
                self._poll_update(now_ts)
            except KeyboardInterrupt:
                print(f"\n[SetupFeed:{self.symbol}] หยุดการทำงานเรียบร้อยแล้ว")
                break
            except Exception:
                print(f"[SetupFeed:{self.symbol}] Error ในรอบ poll:")
                traceback.print_exc()
            time.sleep(POLL_SECONDS)


def _run_one_symbol(symbol: str):
    """รัน engine สำหรับ 1 สัญลักษณ์ — ถ้า engine ล่ม (เช่น API error รุนแรง) ให้ลองใหม่"""
    tag = f"[SetupFeed:{symbol}]"
    while True:
        try:
            engine = SetupFeedEngine(symbol)
            engine.run()
            return  # run() ออกเฉพาะ KeyboardInterrupt
        except KeyboardInterrupt:
            return
        except Exception:
            print(f"{tag} Engine ผิดพลาดรุนแรง — restart ใหม่ใน 10 วิ:")
            traceback.print_exc()
            time.sleep(10)


if __name__ == "__main__":
    if not TRADE_SYMBOLS:
        print("[SetupFeed] ไม่พบ TRADE_SYMBOLS ที่ใช้ได้ — ปิดระบบ")
    else:
        import threading

        print(f"[SetupFeed] เริ่ม Rule-Based สำหรับ {len(TRADE_SYMBOLS)} สัญลักษณ์: "
              f"{', '.join(TRADE_SYMBOLS)}")
        threads = []
        for sym in TRADE_SYMBOLS:
            t = threading.Thread(target=_run_one_symbol, args=(sym,), daemon=True)
            t.start()
            threads.append(t)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[SetupFeed] ปิดโปรแกรม")
