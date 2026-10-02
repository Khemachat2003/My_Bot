# Architecture — การไหลของข้อมูล (Data Flow)

## ผังระบบภาพรวม

```
                    ┌────────────────────────── VPS ──────────────────────────┐
                    │                                                         │
 Deriv API ◄──WS──► deriv_feed.py ◄──เดินแท่ง── setup_feed.py ──สัญญาณ──► setup_db.py
                    │    (symbol fallback)      🔵 11-Checklist                │
                    │                                │                         │
                    │                                ▼                         ▼
                    │                          telegram.py ◄────────────  db.py
                    │                                ▲                         ▲
 macro_feed.py ─► db ──บริบท──► notifier.py ───ml_signals──► ml_forecaster/* ┘
                    │            🟢 (threshold 0.55)      (เทรน/ตรวจ/ยิงเอง)
                    │                                                         │
                    │  api.py (FastAPI) ◄──ทุกตาราง── db.py ──► Dashboard SPA
                    │    │  /static → frontend/  (index.html + vendor/)        │
                    │    │  /api/*  → JSON ทั้งหมด                              │
                    └────┼─────────────────────────────────────────────────────┘
                         │  poll สัญญาณ FIRE
 mt5_state.db ◄──► mt5_executor.py (เครื่อง Windows, MT5 terminal)
                         └──ออเดอร์+SL/TP──► MetaTrader5
```

## การไหลของข้อมูลฝั่ง Rule-Based (🔵 Setup)

1. **Deriv WebSocket** (`data_feed/deriv_feed.py`): เชื่อม `wss://api.derivws.com/...`,
   subscribe ticks M1/M5, มี reconnect + symbol fallback (`frxXAUUSD` → `deriv_XAU/USD`)
2. **เดินแท่ง** (`setup_feed.py`): เก็บแท่งจริงเป็น OHLC → ป้อน `setup_scorer.py`
3. **คะแนน** (`setup_scorer.py`): pure function — คะแนน 11-Checklist + EMA200 Rejection
4. **สัญญาณ**: entry_trigger เปลี่ยน False→True (ไม่ยิงซ้ำในไม้เดิม) → `setup_db.py` เขียน `setup_signals`
5. **แจ้ง**: `telegram.py` ส่ง (retry + log สถานะใน `telegram_log`)
6. **ออเดอร์**: `executor/mt5_executor.py` poll `GET /api/signals?limit=N` (auth Basic) → กรอง PENDING/FIRE → MT5 + SL/TP
   (หมายเหตุ: `db.fetch_pending_setup_signals()` มีอยู่ใน backend แต่**ไม่มี endpoint** `/api/pending_setup_signals` — ตรวจจากโค้ดจริง)

## การไหลของข้อมูลฝั่ง ML (🟢 Notifier)

1. **เทรน/ตรวจ** (`ml_forecaster/`): walk-forward + auto-retrain, features v2 (มีบริบท DXY)
2. **ยิงสัญญาณ**: โมเดลประเมินราคาปัจจุบัน → เขียน `ml_signals` (confidence)
3. **กรอง** (`notifier.py`): confidence >= 0.55 (validate แล้วว่า reproduce ได้) → Telegram
4. **บริบท**: `macro_feed.py` ดึง DXY รายชั่วโมง → ป้อน features

## ตารางข้อมูลหลัก (SQLite WAL — data/bot.db)

| ตาราง | ใครเขียน | ใครอ่าน |
|---|---|---|
| `setup_signals` | setup_feed (+setup_backtest) | api/executor/telegram |
| `ml_signals` | ml_forecaster | notifier/api |
| `notifier_state` | notifier | api |
| `telegram_log` | telegram | api |
| `trade_journal` | api/mt5 | api |
| `macro_dxy_1h` | macro_feed | ml_forecaster |

## ขอบเขตการรู้จักกันของแต่ละฝั่ง

- ระบบ live บน VPS **ไม่ import** `executor/*` และ `scripts/*` — ติดต่อผ่าน API ของ `api.py` เท่านั้น
- `scripts/backtest/*` import `backend.indicators` ได้ (ตัวเดียวกับ live) แต่ live ไม่รู้จัก backtest
- `frontend/index.html` คุยกับ backend ผ่าน `/api/*` เท่านั้น
