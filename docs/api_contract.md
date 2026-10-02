# api_contract.md — สัญญา API ของ dashboard (backend/api.py ⇄ frontend ⇄ executor)

> กฎ: response ของ endpoint เดิม **ห้ามเปลี่ยน shape** — เพิ่ม field ได้ "ต่อท้าย" เท่านั้น
> Auth: ทุก endpoint ยกเว้นที่ระบุ — ใช้ HTTP Basic (API/curl) หรือ session cookie จาก `/login`
> ตัวเรียก: `frontend/src/shared/api/client.js` (จุดเดียว) · `executor/mt5_executor.py` (หากมี) · docker healthcheck

## สาธารณะ (ไม่ต้อง auth)

| Method | Path | ข้อมูลเข้า | คืน | ใครใช้ |
|---|---|---|---|---|
| GET | `/api/health` | - | `{status, service}` | docker healthcheck / deploy script |
| GET | `/login` | - | HTML หน้า login | เบราว์เซอร์ |
| POST | `/login` | JSON `{username, password}` | 303 → `/` + cookie | ฟอร์ม login |
| GET | `/logout` | - | 303 → `/login` | ปุ่ม "ออกจากระบบ" |

## ข้อมูลราคา/ตลาด

| Method | Path | ข้อมูลเข้า | คืน | ใครใช้ |
|---|---|---|---|---|
| GET | `/api/symbol` | - | สัญลักษณ์ที่ระบบใช้จริง (มี fallback ตลาดปิด) | refreshPrice, symbols |
| GET | `/api/symbols` | - | `[{symbol, label}]` รายการที่รองรับ | dropdown กราฟ |
| GET | `/api/candles` | `tf`(1m/5m/15m/30m/1h/4h), `count`(≤1000), `symbol` | `[{t,o,h,l,c,v}]` (cache 30 วิ + fallback resample จาก DB) | กราฟหลัก |
| GET | `/api/watchlist` | `symbols` (คั่น comma, ว่าง = 8 มาตรฐาน) | `[{symbol, price, chgPct}]` (cache 10 วิ + staleness guard) | Watchlist |
| GET | `/api/prices` | `limit`(≤5000), `symbol` | ราคา 1m ย้อนหลังจาก DB | (สำรอง) |

## สัญญาณ Rule-Based (🔵 System 1)

| Method | Path | ข้อมูลเข้า | คืน |
|---|---|---|---|
| GET | `/api/signals` | `limit`(≤1000), `symbol?` | รายการสัญญาณ (ล่าสุดก่อน) — schema ตาม `db.fetch_recent_setup_signals` |
| GET | `/api/signals/markers` | `symbol`, `limit`(≤200) | markers สำหรับกราฟ (entry/SL/TP/ผล) |
| GET | `/api/ticktouch/stats` | - | สถิติ research แตะ EMA200 3 เคส + น้ำหนัก checklist |
| GET | `/api/stats` | `payout`(0.82) | winrate รวม + Wilson CI + margin |
| GET | `/api/stats/by_timeframe` | `payout` | `{M1: {...}, M5: {...}}` |
| GET | `/api/setup/latest` | `symbol` | คะแนน 11-Checklist ล่าสุดของสัญลักษณ์ |
| GET | `/api/setup/latest-all` | - | ล่าสุดทุกสัญลักษณ์ × M1/M5 |
| GET | `/api/setup/history` | `timeframe`(M1/M5), ... | ประวัติ checklist |

## สัญญาณ ML (🟢 System 2)

| Method | Path | ข้อมูลเข้า | คืน |
|---|---|---|---|
| GET | `/api/ml/signals` | `limit` | รายการสัญญาณ ML (schema ตาม `db.fetch_recent_ml_signals`) |
| GET | `/api/ml/stats` | `payout` | winrate + CI + margin |
| GET | `/api/ml/stats/by_timeframe` | `payout` | `{M1, M5}` |
| GET | `/api/ml/latest` | - | `{M1: {prob_up, prob_down, signal, confidence, ...}, M5: ...}` → gauge/topbar |

## Journal / P&L / CFD

| Method | Path | ข้อมูลเข้า | คืน |
|---|---|---|---|
| GET | `/api/journal` | `limit` | รายการเทรดทั้งหมด |
| GET | `/api/journal/stats` | `payout` | KPI + equity curve + daily breakdown |
| GET | `/api/journal/settings` | - | `{capital, stake, currency, ...}` |
| POST | `/api/journal/settings` | JSON `{capital, stake, currency, ...}` | บันทึกตั้งค่า (validate > 0) |
| GET | `/api/journal/report` | - | P&L เป็นเงินจริง แยก ALL/ML/SETUP รายวัน/สัปดาห์/เดือน/ปี |
| GET | `/api/journal/export` | `start?`, `end?` (YYYY-MM-DD) | ไฟล์ .xlsx |
| GET | `/api/models` | - | model registry (version โมเดลที่เคยเทรน) |
| GET | `/api/cfd/backtest` | `signal_type`(ALL/ML/SETUP), ... | ผลจำลอง CFD + เทียบ TP1/TP2 + trades |
| GET | `/api/cfd/paper` | - | สถิติ paper real-time + open/resolved trades |

## หน้าเว็บ

| Method | Path | คืน |
|---|---|---|
| GET | `/` | `frontend/dist/index.html` (auth) — fallback `_archive/index.legacy.html` ถ้ายังไม่ได้ build |
| GET | `/static/*` | ไฟล์ใน `frontend/` (vendor + dist/assets) |

## สิ่งที่ระบบ *ยังไม่มี* (ต้องขออนุญาตก่อนเพิ่ม)

- endpoint สั่งงานเทรด (kill switch, ปิดออเดอร์, แก้ SL/TP) — ปุ่มใน UI ต้องรอ backend ทำก่อน
- สถานะการส่ง Telegram ต่อสัญญาณ (มีตาราง `telegram_log` แต่ยังไม่มี endpoint สรุปให้ UI)
