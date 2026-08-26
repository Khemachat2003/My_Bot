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
from backend.market_hours import is_forex_like, market_open_now, symbol_label, get_session
from backend.ml_forecaster.features_v2 import get_latest_features
from backend.ml_forecaster.setup_features import (
    SETUP_FEATURE_COLUMNS, flatten_setup_result,
)

MODEL_DIR = Path(__file__).resolve().parent / "ml_forecaster"
DATA_DIR = ROOT_DIR / "data"

# ── Config จาก .env ──────────────────────────────────────────────────────────
POLL_SECONDS = int(os.getenv("ML_POLL_SECONDS", "60"))
DERIV_SYMBOL = os.getenv("DERIV_SYMBOL", "frxXAUUSD")
BACKUP_SYMBOL = os.getenv("DERIV_SYMBOL_BACKUP", "R_100")

# แต่ละ timeframe: ถือออเดอร์กี่นาที / resample กี่นาที / ใช้โมเดลไฟล์ไหน / เทรน horizon กี่แท่ง
ML_TIMEFRAMES = [
    {"label": "M1", "hold_min": 15, "resample_min": 1,
     "model_file": "model_m1.joblib", "train_horizon": 15, "min_bars": 150},
    {"label": "M5", "hold_min": 30, "resample_min": 5,
     "model_file": "model_m5.joblib", "train_horizon": 6, "min_bars": 60},
]

# ── Guards (เหมือนฝั่ง rulebase) ──
ML_DAILY_CAP = int(os.getenv("ML_DAILY_CAP", "20"))     # ไม่เกิน 20 ไม้/วัน
ML_COOLDOWN_MIN = float(os.getenv("ML_COOLDOWN_MIN", "60"))  # 60 นาที/direction


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
    """ลำดับ: .env ML_CONF_THRESHOLD (อ่านสดทุกครั้ง — แก้ .env แล้วไม่มีผลทันที
    โดยไม่ต้อง restart) > chosen_conf จากโมเดล > 0.55"""
    import os as _os
    raw = _os.getenv("ML_CONF_THRESHOLD")
    if raw and raw.strip():
        try:
            return float(raw)
        except ValueError:
            pass
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
        self._last_price: float | None = None

    def _evaluate_timeframe(self, df_tf: pd.DataFrame, cfg: dict) -> dict | None:
        """ทำนาย probability ของแท่งล่าสุดด้วยโมเดลของ timeframe นี้"""
        model_cfg = MODELS[cfg["label"]]
        model_features = list(model_cfg.get("features") or [])
        features_df = get_latest_features(
            df_tf,
            feature_columns=model_features,
            floor_minutes=cfg["resample_min"],
        )
        if features_df is None or features_df.empty:
            return None

        # Hybrid: ถ้าโมเดลถูกเทรนด้วย setup-context features (st_*) ต้องคำนวณ
        # score_setup ณ ตอนนี้ แล้ว merge เข้า feature vector — กัน feature mismatch
        has_setup = any(c.startswith("st_") for c in model_features)
        if has_setup:
            try:
                from backend.setup_scorer import score_setup
                setup_result = score_setup(
                    df_tf, timeframe=cfg["label"],
                    target_hold_minutes=cfg["hold_min"],
                )
                setup_vec = flatten_setup_result(setup_result)
                for c in model_features:
                    if c.startswith("st_"):
                        if c not in features_df.columns:
                            features_df[c] = 0.0
                        features_df.loc[features_df.index[-1], c] = setup_vec.get(c, 0.0)
            except Exception:
                import traceback
                print("[MLFeed] setup features error:")
                traceback.print_exc()
                # ถ้าคำนวณ setup ไม่ได้ → กัน prediction ผิด ให้ข้ามรอบนี้
                return None

        model = model_cfg["model"]
        # จัดคอลัมน์ให้ตรงกับ model ที่เทรน (เรียงตาม features list) — กัน mismatch
        for c in model_features:
            if c not in features_df.columns:
                features_df[c] = 0.0
        features_df = features_df[model_features]
        prob_up = float(model.predict_proba(features_df)[0][1])
        prob_down = 1.0 - prob_up
        thresh = _conf_threshold(cfg["label"])

        if prob_up >= thresh:
            signal, confidence = "CALL", prob_up
        elif prob_down >= thresh:
            signal, confidence = "PUT", prob_down
        else:
            signal, confidence = "NEUTRAL", max(prob_up, prob_down)

        # เก็บ feature vector ตอนยิงไว้ 2 จุดประสงค์:
        #   1. log ตอนยิงสัญญาณว่ามองเห็นอะไร
        #   2. auto_retrain เรียนจากสัญญาณจริงที่แพ้/ชนะพร้อม features ตอนนั้น
        features = {
            k: (float(v) if hasattr(v, "item") else v)
            for k, v in features_df.iloc[-1].to_dict().items()
        }

        return {
            "signal": signal, "confidence": confidence,
            "prob_up": prob_up, "prob_down": prob_down,
            "threshold": thresh, "model_version": cfg["model_file"],
            "features": features,
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
                    res = "WIN" if last_price > entry_price else (
                        "LOSE" if last_price < entry_price else "DRAW")
                else:
                    res = "WIN" if last_price < entry_price else (
                        "LOSE" if last_price > entry_price else "DRAW")

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
                if res == "WIN":
                    result_icon = "🟢 WIN"
                elif res == "LOSE":
                    result_icon = "🔴 LOSE"
                else:
                    result_icon = "🟡 DRAW"
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

        try:
            cfd_resolved = db.check_cfd_trades(last_price, now.isoformat(), symbol=DERIV_SYMBOL)
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
                print(f"[MLFeed] CFD #{cr['id']} → {cr['result']} P&L=${cr.get('pnl',0):+.2f}")
        except Exception:
            pass

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
        # ML เทรนจากข้อมูล XAUUSD เท่านั้น → เทรดเฉพาะ symbol หลัก ไม่สลับไป R_100
        # (R_100 เป็นสินทรัพย์สังเคราะห์คนละประเภท — ยกเลิกการสลับตามที่ตกลง)
        symbol = DERIV_SYMBOL
        if is_forex_like(symbol) and not market_open_now():
            now = pd.Timestamp.now(tz="UTC")
            self._resolve_pending(now, self._last_price or 0.0)
            return
        self._active_symbol = symbol
        self._last_signal_state = {}   # รีเซ็ตกันสแปม

        raw_df = fetch_live_or_cache_candles(symbol, count=500)
        if raw_df.empty or len(raw_df) < 100:
            print("[MLFeed] ข้อมูลราคาไม่พอ ข้ามรอบนี้")
            return

        last_price = float(raw_df["close"].iloc[-1])
        self._last_price = last_price
        candle_time = raw_df.index[-1]
        now = pd.Timestamp.now(tz="UTC")

        # เก็บแท่งล่าสุดลง prices (ตารางร่วมสำหรับกราฟ Dashboard) — แยก symbol
        # กัน XAUUSD ปนกับ R_100 (สำรอง) ในตารางเดียวจนกราฟ scale เพี้ยน
        last_row = raw_df.iloc[-1]
        db.insert_price(
            pd.Timestamp(candle_time).isoformat(),
            float(last_row["open"]), float(last_row["high"]),
            float(last_row["low"]), float(last_row["close"]),
            symbol=symbol,
        )
        # backfill ราคาย้อนหลัง (เฉพาะครั้งแรก/ครั้งแรกของ symbol ใหม่)
        # กันกราฟ Dashboard ว่างบนเครื่องที่เพิ่งเริ่ม เช่น VPS
        if getattr(self, "_backfilled_symbol", None) != symbol:
            n = db.backfill_prices(raw_df, symbol=symbol)
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
                # 🚦 Night block: 18-24 UTC volume ต่ำ (rulebase พิสูจน์แล้ว WR 34-46%)
                if get_session(now) == "Night":
                    print(f"[MLFeed] ข้ามสัญญาณ [{cfg['label']}] — Night session "
                          f"(volume ต่ำ, WR ต่ำกว่า breakeven)")
                    continue
                # 🚦 daily cap: ไม่เกิน 20 ไม้/วัน
                start_of_day = pd.Timestamp(
                    now.tz_localize(None) if now.tz is not None else now
                ).normalize().isoformat()
                day_count = db.count_ml_signals_since(start_iso=start_of_day)
                if day_count >= ML_DAILY_CAP:
                    print(f"[MLFeed] ข้ามสัญญาณ [{cfg['label']}] — ถึง daily cap "
                          f"{ML_DAILY_CAP} แล้ว ({day_count} ไม้)")
                    continue
                # 🚦 cooldown: 60 นาที/direction (กันยิงซ้ำทิศเดิมถี่ๆ)
                recent_same_dir = [s for s in db.fetch_recent_ml_signals(limit=10)
                                   if s.get("direction") == res["signal"]]
                if recent_same_dir:
                    age_min = (now - pd.to_datetime(
                        recent_same_dir[0]["signal_time"])).total_seconds() / 60.0
                    if age_min < ML_COOLDOWN_MIN:
                        print(f"[MLFeed] ข้ามสัญญาณ [{cfg['label']}] — cooldown "
                              f"{res['signal']} {age_min:.0f}/{ML_COOLDOWN_MIN} นาที")
                        continue
                # 🚦 loss-streak cooldown: แพ้ 2 ไม้ติด → พัก 1 ชม.
                recent_ml = [s for s in db.fetch_recent_ml_signals(limit=4)
                             if s.get("result") in ("WIN", "LOSE")]
                if (len(recent_ml) >= 2
                        and all(s["result"] == "LOSE" for s in recent_ml[:2])):
                    last_loss_time = pd.to_datetime(recent_ml[0]["signal_time"])
                    loss_age_min = (now - last_loss_time).total_seconds() / 60.0
                    if loss_age_min < 60.0:
                        print(f"[MLFeed] ข้ามสัญญาณ [{cfg['label']}] — "
                              f"แพ้ 2 ไม้ติด หยุด 1 ชม. (เหลือ {60 - loss_age_min:.0f} นาที)")
                        continue
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
                            features=res.get("features"),
                        )
                        print(f"[MLFeed] บันทึกสัญญาณ ID #{new_sig_id} [{cfg['label']}] ลง ml_signals "
                              f"(รอวัดผลในอีก {hold_min} นาที)")
                        db.insert_cfd_paper_trade(
                            signal_id=new_sig_id, signal_type="ML",
                            symbol=symbol, direction=res["signal"],
                            entry_price=last_price, entry_time=now.isoformat(),
                        )
                    except Exception:
                        print("[MLFeed] ไม่สามารถบันทึกสัญญาณลง DB ได้:")
                        traceback.print_exc()

                    sym_text = symbol_label(symbol)
                    if symbol != DERIV_SYMBOL:
                        sym_text = f"{sym_text} (สำรอง — ตลาดทองปิด)"
                    ps = db.get_pip_size(symbol)
                    spread = db.CFD_SPREAD_PIPS * ps
                    eff = last_price + spread/2 if res["signal"] == "CALL" else last_price - spread/2
                    if res["signal"] == "CALL":
                        cfd_sl = eff - db.CFD_SL_PIPS * ps
                        cfd_tp1 = eff + db.CFD_TP1_PIPS * ps
                        cfd_tp2 = eff + db.CFD_TP2_PIPS * ps
                    else:
                        cfd_sl = eff + db.CFD_SL_PIPS * ps
                        cfd_tp1 = eff - db.CFD_TP1_PIPS * ps
                        cfd_tp2 = eff - db.CFD_TP2_PIPS * ps
                    pv = db.get_pip_value(symbol)
                    lot = db._cfd_lot_size(symbol)
                    msg = (
                        f"🟢 [ML MODEL ALERT]\n"
                        f"Symbol: {sym_text} | TF: {cfg['label']} | Direction: {res['signal']}\n"
                        f"Entry: {last_price:.2f} | Win Prob: {res['confidence']:.1%} | Hold: {hold_min}m\n"
                        f"เวลาเข้า: {now.strftime('%H:%M:%S')} UTC\n"
                        f"─── CFD Paper Trade ───\n"
                        f"Entry (eff): {eff:.5f} | Lot: {lot}\n"
                        f"SL: {cfd_sl:.5f} | TP1: {cfd_tp1:.5f} | TP2: {cfd_tp2:.5f}\n"
                        f"Risk: ${db.CFD_CAPITAL * db.CFD_RISK_PCT:.0f} (1%)\n"
                        f"TP1 Reward: ${db.CFD_TP1_PIPS * pv * lot:.2f}\n"
                        f"TP2 Reward: ${db.CFD_TP2_PIPS * pv * lot:.2f}"
                    )
                    ok = send_telegram(msg)
                    print(f"[MLFeed] Telegram ALERT [{cfg['label']}] {'ส่งสำเร็จ' if ok else 'ส่งไม่สำเร็จ (ดู log ด้านบน)'}")

            self._last_signal_state[cfg["label"]] = res["signal"]

    def run(self):
        print("=== 🟢 เริ่มต้นระบบ ML Model Engine (Real-time Context 500 แท่ง, M1/M5) ===")
        print(f"    poll={POLL_SECONDS}s | threshold={_conf_threshold('M1')} "
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
