# XAUUSD Trading Bot — Live Signal System (Deriv + ML + MT5)

ระบบเทรดทอง XAUUSD แบบ live ครบวงจร: ยิงสัญญาณเข้า Telegram, Dashboard เว็บ,
โมเดล ML (LightGBM) แยกตาม timeframe, และ MT5 Executor ส่งออเดอร์จริงพร้อม SL/TP

> ⚠️ **หมายเหตุสำคัญ:** ระบบนี้เป็นเครื่องมือช่วยตัดสินใจ ไม่ใช่การรับประกันกำไร
> การเทรด Forex/ทองคำมีความเสี่ยงสูง — ทดสอบด้วย Demo/phantom mode ก่อนเสมอ

## สถาปัตยกรรม (3 ระบบ + Executor)

รันพร้อมกันด้วย supervisor เดียว (`run_live.py`) — ถ้า process ไหนตาย restart ให้อัตโนมัติ

| ระบบ | โมดูล | หน้าที่ |
|---|---|---|
| 🔵 Rule-Based Setup Engine | `backend.setup_feed` + `backend.setup_scorer` | สัญญาณ Sniper Reversion ตาม 11-Checklist (EMA200/EMA100 touch) → Telegram |
| 🟢 ML Model Engine | `backend.notifier` | LightGBM per-timeframe (`model_m1/m5.joblib`) + dynamic threshold → Telegram |
| 🌐 Dashboard | `backend.api` (FastAPI) | กราฟ multi-pane, S/R editor, Equity Curve, login ด้วย session cookie |
| 🏦 MT5 Executor | `mt5_executor.py` (Windows) | ดึงสัญญาณ FIRE จาก VPS → ส่งออเดอร์ MT5 พร้อม SL/TP (fractal + R:R) |
| 🌍 Macro Feed | `backend.macro_feed` | ดึง DXY รายชั่วโมงจาก Yahoo → ตาราง `macro_1h` (Regime-Gate) |
| 💾 Backup | `backend.backup` | zip DB + models + candles ส่งเข้า Telegram ทุก 6 ชม. |

**Data feed:** `backend/data_feed/deriv_feed.py` เป็นตัวเดียวที่ดึงข้อมูลจาก Deriv
(WebSocket, timeout 15s, cache CSV, fallback symbol อัตโนมัติเมื่อตลาดทองปิด)

## โครงสร้างโปรเจค

```
xauusd-bot/
├── run_live.py             ← รันทุกระบบด้วยคำสั่งเดียว (supervisor + auto-restart)
├── run_backtest.py         ← backtest rule-based (Phase 1)
├── mt5_executor.py         ← MT5 order executor (Windows เท่านั้น)
├── backend/
│   ├── api.py              ← Dashboard (FastAPI + basic auth + session cookie)
│   ├── db.py               ← SQLite (WAL mode): setup_signals, ml_signals, trade_journal...
│   ├── setup_feed.py       ← 🔵 Rule-Based live engine
│   ├── setup_scorer.py     ← 11-Checklist scoring logic
│   ├── notifier.py         ← 🟢 ML live engine
│   ├── setup_db.py         ← ตารางฝั่ง Rule-Based
│   ├── market_hours.py     ← เช็คเวลาเปิด/ปิดตลาด + symbol fallback
│   ├── telegram.py         ← ส่งแจ้งเตือน (retry + log สถานะ)
│   ├── macro_feed.py       ← DXY รายชั่วโมง → DB
│   ├── backup.py           ← backup อัตโนมัติ
│   ├── data_feed/
│   │   ├── deriv_feed.py   ← Deriv WebSocket feed (ตัวจริงตัวเดียว)
│   │   ├── backfill.py     ← ดึงข้อมูลย้อนหลังเป็น CSV
│   │   └── macro_feed.py   ← backfill correlated assets (yfinance, สำหรับ research)
│   └── ml_forecaster/      ← เทรน/ตรวจโมเดล (walk-forward, auto-retrain, features v2)
├── frontend/index.html     ← Dashboard SPA (ใช้ lightweight-charts)
├── scripts/                ← สคริปต์เช็คการเชื่อมต่อ (test_connection ฯลฯ)
├── data/                   ← SQLite DB + CSV cache (git-ignored)
├── docker-compose.yml      ← deploy บน VPS
└── .github/workflows/      ← auto-deploy เมื่อ push main
```

## ติดตั้งและรัน (เครื่อง dev)

```bash
pip install -r requirements.txt
cp .env.example .env        # แล้วเติมค่า TELEGRAM_BOT_TOKEN ฯลฯ

python run_live.py          # รันทุกระบบ (api + setup_feed + notifier + macro + retrain)
python run_live.py --no-api # เทรด headless ไม่เปิด dashboard
```

Dashboard: `http://localhost:8000` (login ด้วย DASHBOARD_USER/DASHBOARD_PASS ใน .env)

> 🔐 **ความปลอดภัย:** หากยังใช้ user/pass เริ่มต้น (`admin`/`change-me-please`)
> ระบบจะอนุญาตให้ login **จาก localhost เท่านั้น** — ก่อน deploy ขึ้น VPS ให้ตั้ง
> `DASHBOARD_USER`/`DASHBOARD_PASS` ใหม่ใน .env เสมอ

## เทรนโมเดล ML

```bash
python -m backend.data_feed.backfill --days 60                    # ดึงข้อมูลย้อนหลัง
python -m backend.ml_forecaster.train_live_models                 # เทรน model_m1/m5
python -m backend.ml_forecaster.train_walkforward --horizon 5     # ตรวจแบบ walk-forward
python -m backend.ml_forecaster.auto_retrain                      # เรียนจากสัญญาณจริง (รันใน run_live แล้ว)
```

ควรมีข้อมูลอย่างน้อย 30-90 วัน (M1) ก่อนเชื่อผลโมเดล — ข้อมูลน้อย AUC จะใกล้ 0.5

## MT5 Executor (Windows)

```bash
pip install MetaTrader5
python mt5_executor.py --dry-run   # ทดสอบโดยไม่ส่งออเดอร์จริง
python mt5_executor.py             # ต้องเปิด MT5 terminal + login ก่อน
```

ตั้งค่าความเสี่ยงใน .env: `MT5_RISK_PCT=0.5`, `MT5_RR=2.0`, `MT5_DAILY_MAX=20` (ดู .env.example ทั้งหมด)

## Deploy ขึ้น VPS (Docker)

```bash
# บน VPS (ครั้งแรก)
git clone https://github.com/Khemachat2003/My_Bot.git /opt/xauusd-bot
cd /opt/xauusd-bot && cp .env.example .env && nano .env
docker compose up -d --build
```

หลังจากนั้นทุก `git push main` → GitHub Actions จะ deploy ให้อัตโนมัติ
(ตั้ง Secrets: `VPS_HOST`, `VPS_USER`, `SSH_KEY` — ดูรายละเอียดใน workflow)

## วินัยการเทรดที่ระบบบังคับ

- Cooldown ต่อ direction + daily cap ต่อทั้ง ML และ Rule-Based
- สัญญาณเก่าเกิน `MT5_MAX_AGE_MIN` นาที → ข้าม
- Cooldown พิเศษช่วงตลาดเพิ่งเปิด (`SETUP_MARKET_OPEN_COOLDOWN_MINUTES`)
- Phantom mode บันทึกสัญญาณทดลองโดยไม่ส่งออเดอร์จริง

