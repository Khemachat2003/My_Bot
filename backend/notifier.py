"""
notifier.py — 🟢 System 2: ML Research & Confidence Model Engine
===================================================================================
รันแยก process:  python -m backend.notifier   (หรือผ่าน run_live.py รวม 3 ระบบ)

หน้าที่:
  1. ดึง Live Candles ย้อนหลัง 500 แท่ง (1m) จาก Deriv ทุก 60 วินาที
     (สลับ symbol อัตโนมัติเป็นตัวสำรอง R_100 เมื่อตลาดทองจริงปิดเสาร์-อาทิตย์)
  2. คำนวณ Feature ผ่านโมเดลที่เทรนแยกตาม timeframe ให้ตรงกับเวลาถือจริง:
       M1 (native 1m)  → model_m1.joblib (horizon 15 = ถือ 15 นาที)
       M5 (resample 5m)→ model_m5.joblib (horizon 6  = ถือ 30 นาที)
     ถ้ายังไม่ได้รัน train_live_models.py จะ fallback ไปใช้ model_v2.joblib เดิม
     (พร้อมคำเตือนว่าค่า confidence อาจไม่ตรงกับเวลาถือ)
  3. เมื่อ model_prob ข้าม Dynamic Threshold (ML_CONF_THRESHOLD ใน .env) และเปลี่ยน
     ทิศทางจากรอบก่อน (กันสแปม) → บันทึกลงตาราง ml_signals (db.py) และยิง Telegram
  4. เมื่อสัญญาณ PENDING ครบเวลาถือออเดอร์ → ประเมินผล WIN/LOSE บันทึกลง DB
     และยิง Telegram [RESULT] [ML]
  5. อัปเดตค่า prob_up/prob_down ล่าสุดต่อ timeframe ลง ml_latest สำหรับ
     Real-time Probability Gauge บน Dashboard

⚠️ ระบบนี้แยกขาดจาก 🔵 Rule-Based Setup Engine (setup_feed.py) โดยสมบูรณ์:
   ไม่ใช้ตาราง setup_signals/setup_scores, ไม่ import setup_scorer
"""
from __future__ import annotations

import os
import sys
import time
import traceback
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# ป้องกัน print ภาษาไทย/emoji แล้ว crash เมื่อ console เป็น cp1252
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import joblib
import pandas as pd

from backend import db
from backend.telegram import send_telegram
from backend.market_hours import choose_symbol, symbol_label
from backend.ml_forecaster.features_v2 import get_latest_features

MODEL_DIR = Path(__file__).resolve().parent / "ml_forecaster"
DATA_DIR = ROOT_DIR / "data"

# ── Config จาก .env ──────────────────────────────────────────────────────────
POLL_SECONDS = int(os.getenv("ML_POLL_SECONDS", "60"))
ENV_CONF = os.getenv("ML_CONF_THRESHOLD")
ENV_CONF = float(ENV_CONF) if ENV_CONF and ENV_CONF.strip() else None
DERIV_SYMBOL = os.getenv("DERIV_SYMBOL", "frxXAUUSD")
BACKUP_SYMBOL = os.getenv("DERIV_SYMBOL_BACKUP", "R_100")

# แต่ละ timeframe: ถือออเดอร์กี่นาที / resample กี่นาที / ใช้โมเดลไฟล์ไหน / เทรน horizon กี่แท่ง
ML_TIMEFRAMES = [
    {"label": "M1", "hold_min": 15, "resample_min": 1,
     "model_file": "model_m1.joblib", "train_horizon": 15, "min_bars": 150},
    {"label": "M5", "hold_min": 30, "resample_min": 5,
     "model_file": "model_m5.joblib", "train_horizon": 6, "min_bars": 60},
]


def _load_model_bundle(cfg: dict) -> dict:
    """โหลดโมเดลของ timeframe นี้ — ชอบไฟล์ per-timeframe ใหม่; ถ้าไม่มีค่อยใช้ model_v2.joblib เดิม"""
    model_path = MODEL_DIR / cfg["model_file"]
    if model_path.exists():
        bundle = joblib.load(model_path)
        print(f"🚀 Loaded {cfg['model_file']} | horizon={bundle.get('horizon')} | "
              f"conf={bundle.get('chosen_conf')}")
        return {"model": bundle["model"], "features": bundle.get("features"),
                "horizon": bundle.get("horizon", cfg["train_horizon"]),
                "chosen_conf": bundle.get("chosen_conf", 0.55)}

    legacy = MODEL_DIR / "model_v2.joblib"
    if legacy.exists():
        bundle = joblib.load(legacy)
        print(f"⚠️ ไม่พบ {cfg['model_file']} — ใช้ model_v2.joblib (horizon={bundle.get('horizon')}) แทน "
              f"โปรดรัน `python -m backend.ml_forecaster.train_live_models` เพื่อให้ confidence ตรงกับ "
              f"เวลาถือ {cfg['hold_min']} นาทีของ TF {cfg['label']}")
        return {"model": bundle["model"], "features": bundle.get("features"),
                "horizon": bundle.get("horizon"), "chosen_conf": bundle.get("chosen_conf", 0.55)}

    raise FileNotFoundError(
        f"ไม่พบโมเดล {cfg['model_file']} หรือ model_v2.joblib ใน {MODEL_DIR}\n"
        f"โปรดรัน: python -m backend.ml_forecaster.train_live_models"
    )


def _conf_threshold(label: str) -> float:
    """ลำดับ: .env ML_CONF_THRESHOLD > chosen_conf จากโมเดล > 0.55"""
    if ENV_CONF is not None:
        return ENV_CONF
    return MODELS[label].get("chosen_conf") or 0.55


def _load_models_safe() -> dict:
    """โหลดโมเดลทุก TF — ถ้าตัวไหน fail จะ log แล้วข้ามตัวนั้น ไม่ทำให้ process ทั้งหมดตาย
    (เดิม load ที่ module level → โมเดลตัวเดียวพัง = notifier ตาย = ml_latest/Prob Gauge
    บน Dashboard ว่างตลอดทั้งที่ container ยัง healthy เพราะ healthcheck ตรวจแค่ API)"""
    loaded: dict = {}
    for cfg in ML_TIMEFRAMES:
        try:
            loaded[cfg["label"]] = _load_model_bundle(cfg)
        except Exception as e:
            print(f"❌ [MLFeed] ไม่สามารถโหลดโมเดล TF:{cfg['label']} ({e}) — "
                  f"ข้าม TF นี้ไป (Dashboard Prob Gauge ของ TF นี้จะว่าง)")
    return loaded


MODELS = _load_models_safe()


def fetch_live_or_cache_candles(symbol: str, count: int = 500, retries: int = 3) -> pd.DataFrame:
    """ดึงข้อมูลราคา Real-time ย้อนหลัง count แท่ง (ลองใหม่ 3 ครั้ง) หากดึง API ไม่สำเร็จ
    จะ Fallback ไปใช้ Cache CSV"""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            from backend.data_feed.deriv_feed import fetch_candles_history
            df = fetch_candles_history(symbol=symbol, granularity=60, count=count)
            if df is not None and not df.empty:
                return _ensure_utc(df)
        except Exception as e:
            last_err = e
            print(f"[MLFeed] ดึง API ครั้งที่ {attempt}/{retries} ไม่สำเร็จ: {e}")
            time.sleep(5 * attempt)

    cache_path = DATA_DIR / f"deriv_{symbol}_60s.csv"
    if cache_path.exists():
        print(f"[MLFeed] Fallback ใช้ Cache: {cache_path}")
        df = pd.read_csv(cache_path, index_col="datetime", parse_dates=True)
        return _ensure_utc(df.tail(count))

    raise FileNotFoundError(f"ไม่สามารถดึง API ({last_err}) และไม่พบ Cache ที่ {cache_path}")


def _ensure_utc(df: pd.DataFrame) -> pd.DataFrame:
    """ปรับ index ให้เป็น tz-aware UTC เสมอ (กันเวลา naive/aware ปนกันจน feature พัง)"""
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def _resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 1:
        return df
    rule = f"{minutes}min"
    o = df["open"].resample(rule, closed="left", label="left", origin="epoch").first()
    h = df["high"].resample(rule, closed="left", label="left", origin="epoch").max()
    l = df["low"].resample(rule, closed="left", label="left", origin="epoch").min()
    c = df["close"].resample(rule, closed="left", label="left", origin="epoch").last()
    v = df["volume"].resample(rule, closed="left", label="left", origin="epoch").sum() if "volume" in df else None
    parts = [o, h, l, c] + ([v] if v is not None else [])
    out = pd.concat(parts, axis=1)
    out.columns = ["open", "high", "low", "close"] + (["volume"] if v is not None else [])
    return out.dropna()


class MLFeedEngine:
    def __init__(self):
        db.init_db()
        self._last_signal_state: dict[str, str] = {}
        self._active_symbol: str | None = None
        self._symbol_switch_notified = False

    def _evaluate_timeframe(self, df_tf: pd.DataFrame, cfg: dict) -> dict | None:
        """ทำนาย probability ของแท่งล่าสุดด้วยโมเดลของ timeframe นี้"""
        model_cfg = MODELS[cfg["label"]]
        features_df = get_latest_features(
            df_tf,
            feature_columns=model_cfg["features"],
            floor_minutes=cfg["resample_min"],
        )
        if features_df is None or features_df.empty:
            return None

        model = model_cfg["model"]
        prob_up = float(model.predict_proba(features_df)[0][1])
        prob_down = 1.0 - prob_up
        thresh = _conf_threshold(cfg["label"])

        if prob_up >= thresh:
            signal, confidence = "CALL", prob_up
        elif prob_down >= thresh:
            signal, confidence = "PUT", prob_down
        else:
            signal, confidence = "NEUTRAL", max(prob_up, prob_down)

        return {
            "signal": signal, "confidence": confidence,
            "prob_up": prob_up, "prob_down": prob_down,
            "threshold": thresh, "model_version": cfg["model_file"],
        }

    # 🏁 ตรวจสัญญาณ PENDING ที่ครบเวลาถือออเดอร์ → ประเมิน WIN/LOSE
    def _resolve_pending(self, now: pd.Timestamp, last_price: float):
        try:
            pending = db.fetch_pending_ml_signals()
            for row in pending:
                sig_time = pd.to_datetime(row["signal_time"])
                elapsed_min = (now - sig_time).total_seconds() / 60.0
                if elapsed_min < row["horizon_min"]:
                    continue

                entry_price = row["entry_price"]
                direction = row["direction"]
                if direction == "CALL":
                    res = "WIN" if last_price > entry_price else "LOSE"
                else:
                    res = "WIN" if last_price < entry_price else "LOSE"

                db.update_ml_signal_result(row["id"], last_price, res)

                # mirror ลง trade_journal (เก็บ P&L จำลอง)
                trade_id = db.insert_trade(
                    signal_id=row["id"], signal_type="ML", timeframe=row["timeframe"],
                    symbol=self._active_symbol or DERIV_SYMBOL,
                    direction=direction, entry_price=entry_price,
                    entry_time=row["signal_time"], hold_min=row["horizon_min"],
                    confidence=row["confidence"], model_version=row["model_version"],
                )
                db.update_trade_result(trade_id, last_price, now.isoformat(), res)

                pips_diff = abs(last_price - entry_price)
                result_icon = "🟢 WIN" if res == "WIN" else "🔴 LOSE"
                msg = (
                    f"🏁 [RESULT] [ML MODEL] | ID #{row['id']} | TF: {row['timeframe']}\n"
                    f"ทิศทาง: {direction} | ผลลัพธ์: {result_icon}\n"
                    f"Entry: {entry_price:.2f} ➔ Exit: {last_price:.2f} "
                    f"({'+' if res == 'WIN' else '-'}{pips_diff:.2f})\n"
                    f"ระยะเวลาที่ถือ: {row['horizon_min']} นาที\n"
                    f"เวลาสรุปผล: {now.strftime('%H:%M:%S')} UTC"
                )
                send_telegram(msg)
                print(f"[MLFeed] สรุปผล ID #{row['id']} → {res}")
        except Exception:
            print("[MLFeed] Error ในการสรุปผล PENDING signals:")
            traceback.print_exc()

    def _notify_symbol_switch(self, old_symbol: str, new_symbol: str):
        """แจ้งเมื่อระบบสลับไปใช้สัญลักษณ์สำรอง (เช่น เสาร์-อาทิตย์)"""
        self._symbol_switch_notified = True
        msg = (
            f"🔄 [SYMBOL SWITCH] ระบบสลับสัญลักษณ์อัตโนมัติ\n"
            f"จาก: {symbol_label(old_symbol)} → เป็น: {symbol_label(new_symbol)}\n"
            f"เหตุผล: ตลาดหลักปิดหรือไม่สามารถรับราคาได้ — ระบบยังทำงานต่อด้วยสัญลักษณ์สำรอง"
        )
        send_telegram(msg)

    def run_once(self):
        symbol = choose_symbol()
        if symbol != self._active_symbol:
            if self._active_symbol is not None and not self._symbol_switch_notified:
                self._notify_symbol_switch(self._active_symbol, symbol)
            print(f"[MLFeed] ใช้สัญลักษณ์: {symbol}")
            self._active_symbol = symbol
            self._last_signal_state = {}   # รีเซ็ตกันสแปมเมื่อสลับ symbol

        raw_df = fetch_live_or_cache_candles(symbol, count=500)
        if raw_df.empty or len(raw_df) < 100:
            print("[MLFeed] ข้อมูลราคาไม่พอ ข้ามรอบนี้")
            return

        last_price = float(raw_df["close"].iloc[-1])
        candle_time = raw_df.index[-1]
        now = pd.Timestamp.now(tz="UTC")

        # เก็บแท่งล่าสุดลง prices (ตารางร่วมสำหรับกราฟ Dashboard)
        last_row = raw_df.iloc[-1]
        db.insert_price(
            pd.Timestamp(candle_time).isoformat(),
            float(last_row["open"]), float(last_row["high"]),
            float(last_row["low"]), float(last_row["close"]),
        )
        # backfill ราคาย้อนหลัง (เฉพาะครั้งแรก/ครั้งแรกของ symbol ใหม่)
        # กันกราฟ Dashboard ว่างบนเครื่องที่เพิ่งเริ่ม เช่น VPS
        if getattr(self, "_backfilled_symbol", None) != symbol:
            n = db.backfill_prices(raw_df)
            self._backfilled_symbol = symbol
            print(f"[MLFeed] Backfill ราคาย้อนหลัง {n} แท่งลง prices (กราฟ Dashboard)")

        self._resolve_pending(now, last_price)

        # TF ที่ยังมีสัญญาณค้างรอสรุปผล → กันยิงซ้ำซ้อนใน TF เดียวกัน
        pending_tfs = {row["timeframe"] for row in db.fetch_pending_ml_signals()}

        for cfg in ML_TIMEFRAMES:
            if cfg["label"] not in MODELS:
                continue
            df_tf = _resample(raw_df, cfg["resample_min"])
            if len(df_tf) < cfg["min_bars"]:
                continue

            res = self._evaluate_timeframe(df_tf, cfg)
            if res is None:
                continue

            db.upsert_ml_latest(
                timeframe=cfg["label"], ts=now.isoformat(),
                prob_up=res["prob_up"], prob_down=res["prob_down"],
                signal=res["signal"], confidence=res["confidence"],
                threshold_used=res["threshold"],
            )

            print(
                f"[{now.strftime('%H:%M:%S')}] TF:{cfg['label']} {symbol_label(symbol)} "
                f"Price:{last_price:.2f} Signal:{res['signal']} Conf:{res['confidence']:.2%} "
                f"(Up:{res['prob_up']:.2%} Down:{res['prob_down']:.2%})"
            )

            prev_state = self._last_signal_state.get(cfg["label"], "NEUTRAL")
            if res["signal"] in ("CALL", "PUT") and res["signal"] != prev_state:
                if cfg["label"] in pending_tfs:
                    print(f"[MLFeed] ข้าม TF:{cfg['label']} — ยังมีสัญญาณ PENDING รอสรุปผล (กันซ้อน)")
                else:
                    hold_min = cfg["hold_min"]
                    target_time = (now + pd.Timedelta(minutes=hold_min)).isoformat()
                    try:
                        new_sig_id = db.insert_ml_signal(
                            signal_time=now.isoformat(),
                            entry_price=last_price,
                            direction=res["signal"],
                            confidence=res["confidence"],
                            horizon_min=hold_min,
                            target_time=target_time,
                            timeframe=cfg["label"],
                            prob_up=res["prob_up"],
                            prob_down=res["prob_down"],
                            threshold_used=res["threshold"],
                            model_version=res["model_version"],
                        )
                        print(f"[MLFeed] บันทึกสัญญาณ ID #{new_sig_id} [{cfg['label']}] ลง ml_signals "
                              f"(รอวัดผลในอีก {hold_min} นาที)")
                    except Exception:
                        print("[MLFeed] ไม่สามารถบันทึกสัญญาณลง DB ได้:")
                        traceback.print_exc()

                    sym_text = symbol_label(symbol)
                    if symbol != DERIV_SYMBOL:
                        sym_text = f"{sym_text} (สำรอง — ตลาดทองปิด)"
                    msg = (
                        f"🟢 [ML MODEL ALERT]\n"
                        f"Symbol: {sym_text} | TF: {cfg['label']} | Direction: {res['signal']}\n"
                        f"Entry: {last_price:.2f} | Win Prob: {res['confidence']:.1%} | Hold: {hold_min}m\n"
                        f"เวลาเข้า: {now.strftime('%H:%M:%S')} UTC"
                    )
                    send_telegram(msg)

            self._last_signal_state[cfg["label"]] = res["signal"]

    def run(self):
        print("=== 🟢 เริ่มต้นระบบ ML Model Engine (Real-time Context 500 แท่ง, M1/M5) ===")
        print(f"    poll={POLL_SECONDS}s | threshold={ENV_CONF or 'จากโมเดล'} "
              f"| symbol={DERIV_SYMBOL} (backup={BACKUP_SYMBOL})")
        errors = 0
        while True:
            try:
                self.run_once()
                errors = 0
            except KeyboardInterrupt:
                print("\nหยุดการทำงานระบบ ML Model Engine")
                break
            except Exception as e:
                errors += 1
                print(f"[MLFeed] Error in Live Loop ({errors}x): {e}")
                traceback.print_exc()
            finally:
                time.sleep(POLL_SECONDS)


def main():
    engine = MLFeedEngine()
    engine.run()


if __name__ == "__main__":
    main()
