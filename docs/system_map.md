# แผนที่ระบบเดิม (System Map)

> เอกสารนี้บันทึก "แผนที่ระบบตามที่ค้นพบจริง" ก่อนการ refactor โครงสร้าง — เป็นข้อมูล
> อ้างอิงให้ทีมเข้าใจว่าไฟล์ใดทำหน้าที่อะไร ผูกกับระบบไหน ต่อกับอะไร

## ภาพรวม 2 ระบบหลัก + เครื่องมือเสริม

| ระบบ | ไฟล์ engine | ทำอะไร | อ่าน/เขียนอะไร |
|---|---|---|---|
| 🔵 Setup (Rule-Based) | `backend/setup_feed.py` | เดินแท่ง M1/M5 + 11-Checklist → สร้างสัญญาณ FIRE | เขียน `setup_signals` ผ่าน `setup_db.py` |
| 🟢 Notifier (ML) | `backend/notifier.py` | อ่าน `ml_signals` ที่โมเดลยิง + threshold 0.55 → แจ้ง Telegram | อ่าน `ml_signals`, เขียน `notifier_state` |
| 📊 Dashboard | `backend/api.py` | FastAPI: /static + /api/* + basic auth + session cookie | อ่านทุกตาราง |
| ⚙️ MT5 Executor | `executor/mt5_executor.py` | (Windows) ดึงสัญญาณ FIRE จาก API → ส่งออเดอร์ MT5 + SL/TP | อ่าน API + `.env`, เขียน `mt5_state.db` |

## ผังการทำงานแบบเรียงเวลา (live loop)

1. `run_live.py` เปิดทุก supervisor พร้อม auto-restart (เว้นจังหวะกันโหลดซ้ำ)
2. `setup_feed.py` → `deriv_feed.py` (Deriv WebSocket, symbol fallback `frxXAUUSD`→`deriv_XAU/USD`)
   → เดินแท่ง M1/M5 → `setup_scorer.py` คะแนน 11-Checklist → entry_trigger False→True → บันทึกสัญญาณ
3. `notifier.py` อ่าน `ml_signals` (ที่ `ml_forecaster/` ยิงเองตาม threshold) กรอง confidence >= 0.55 → Telegram
4. `mt5_executor.py` (แยกเครื่อง Windows) poll `GET /api/signals?limit=N` → ดึงสัญญาณ FIRE → MT5 order + SL/TP
   (ไม่มี endpoint `/api/pending_setup_signals` — ฟังก์ชัน `db.fetch_pending_setup_signals()` เป็น internal เท่านั้น)
5. `api.py` เสิร์ฟ dashboard + คำสั่งทั้งหมด

## ตารางไฟล์ระบบหลัก

| ไฟล์ | หน้าที่ | ผูกกับ |
|---|---|---|
| `backend/api.py` | Dashboard + REST API ทั้งหมด | อ่าน DB ทุกตาราง |
| `backend/db.py` | SQLite WAL + ตารางกลาง | ทุก module |
| `backend/setup_db.py` | ตารางฝั่ง Rule-Based (`setup_signals` ฯลฯ) | setup_feed/api/executor |
| `backend/setup_feed.py` | 🔵 live engine (เดินแท่ง + เก็บสัญญาณ) | deriv_feed/telegram |
| `backend/setup_scorer.py` | 11-Checklist scoring logic (pure function) | setup_feed/setup_backtest |
| `backend/notifier.py` | 🟢 ML engine (อ่าน ml_signals → แจ้ง) | db/telegram/macro_feed |
| `backend/market_hours.py` | เวลาเปิด/ปิดตลาด + symbol fallback | setup_feed/mt5_executor |
| `backend/macro_feed.py` | DXY รายชั่วโมง → DB (บริบทให้ ML) | notifier/deriv_feed |
| `backend/telegram.py` | ส่งแจ้งเตือนทุกประเภท (retry + log) | setup_feed/notifier |
| `backend/backup.py` | backup อัตโนมัติ | run_live |
| `backend/indicators.py` | EMA/RSI/ADX/ATR/MACD/BB (ใช้ live + ML + backtest) | ทุกฝั่งวิเคราะห์ |
| `backend/data_feed/deriv_feed.py` | Deriv WebSocket (แท่งจริง/ตาราง history) | setup_feed/mt5_executor |
| `backend/data_feed/backfill.py` | ดึงย้อนหลังเป็น CSV | ml_forecaster/setup_backtest |
| `backend/data_feed/macro_feed.py` | backfill correlated assets (research) | ml_forecaster |
| `backend/ml_forecaster/*` | เทรน/ตรวจ/y ยิง ml_signals | notifier/db |
| `executor/mt5_executor.py` | MT5 order executor (Windows) | API/.env/mt5_state.db |
| `run_live.py` | supervisor เปิดทุก supervisor | ทุก supervisor |
