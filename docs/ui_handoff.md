# UI Handoff — เตรียมข้อมูลสำหรับขั้น UX/UI (Prompt 2)

> เอกสารนี้สรุปให้ทีม UX/UI ทำงานต่อได้ทันที: หน้าจอมีอะไร, API endpoint ไหน,
> ข้อมูลแบบไหน และ **สิ่งที่ห้ามแตะ**

## หน้าจอ (ทั้งหมดอยู่ใน `frontend/index.html` — SPA ไฟล์เดียว ~3,319 บรรทัด)

| ส่วน | หน้าที่ |
|---|---|
| Overview | สรุป P&L, equity curve, winrate ML/Setup, model M1/M5 |
| Chart (lightweight-charts) | กราฟหลัก multi-TF, markers SL/TP, S/R editor, watchlist |
| Signals / Trade log | รายการสัญญาณทั้ง Setup และ ML + ผลลัพธ์ |
| Setup tab | คะแนน 11-Checklist ล่าสุด |
| Prob Gauge | ความน่าจะเป็นจากโมเดล M1/M5 |

ไฟล์ demo กราฟ standalone อยู่ `frontend/demos/` · brief งาน redesign อยู่ `frontend/design/`

## API endpoint ที่ frontend ใช้ (อยู่ใน `backend/api.py` — ตรวจจากโค้ดจริง)

| Endpoint | ทำอะไร |
|---|---|
| `/api/health` | สถานะระบบ (ใช้ docker healthcheck) |
| `/login` (GET/POST), `/logout` | session cookie (HMAC-signed) |
| `/api/symbol`, `/api/symbols` | symbol ที่ใช้อยู่ (มี fallback ตลาดปิด) + รายการที่รองรับ |
| `/api/candles?tf&count&symbol` | แท่งเทียน — tf = 1m/5m/15m/30m/1h/4h, count ≤ 1000 (cache 30 วิ + fallback จาก DB) |
| `/api/watchlist?symbols=` | ราคาล่าสุดหลาย symbol (staleness guard 180 วิ + ดึงสดแทน) |
| `/api/prices?limit&symbol` | ราคา 1m ย้อนหลังจาก DB |
| `/api/signals?limit&symbol` | สัญญาณ Setup (🔵) + `/api/signals/markers` สำหรับกราฟ |
| `/api/ticktouch/stats` | สถิติ research แตะ EMA200 3 เคส |
| `/api/stats`, `/api/stats/by_timeframe` | winrate Setup รวม/แยก TF |
| `/api/setup/latest`, `/api/setup/latest-all`, `/api/setup/history` | คะแนน 11-Checklist ล่าสุด/ประวัติ |
| `/api/ml/signals`, `/api/ml/stats`, `/api/ml/stats/by_timeframe` | สัญญาณ ML (🟢) + สถิติ |
| `/api/ml/latest` | prob_up/prob_down ล่าสุดต่อ TF → Probability Gauge |
| `/api/journal` (+`/stats`, `/settings`, `/report`, `/export`) | trade journal + P&L เป็นเงินจริง |
| `/api/models` | model registry — version โมเดลที่เคยเทรน |
| `/api/cfd/backtest`, `/api/cfd/paper` | จำลองเทรด CFD / paper P&L |
| `/` | เสิร์ฟ `frontend/index.html` |

หมายเหตุ: ทุก endpoint ยกเว้น `/api/health`, `/login`, `/` ต้องผ่าน auth
(HTTP Basic หรือ session cookie) — ดู `require_auth()` ใน `backend/api.py`

## ข้อมูลที่แสดงได้ / โครงสร้าง

- แท่งเทียน: `{datetime, open, high, low, close}` + volume (บาง symbol)
- สัญญาณ: `{signal_time, entry_price, direction, confidence, horizon_min,
  target_time, timeframe, score, result}` (ดู `backend/db.py` สำหรับ schema เต็ม)
- ระบบบังคับ timezone UTC ทุก timestamp

## ⛔ สิ่งที่ห้ามแตะ (ความเสี่ยงระบบเทรด)

1. **ห้ามแตะตรรกะใน `backend/setup_scorer.py` / `setup_feed.py` / `notifier.py`** —
   พฤติกรรมสัญญาณต้องเหมือนเดิม 100% (มี characterization tests 63 เคสครอบ)
2. **ห้ามเปลี่ยน shape/response ของ `/api/*` ที่มีอยู่** ให้ frontend ปรับตาม backend
   (ถ้าต้องเพิ่ม field ให้เพิ่ม "ต่อท้าย" ไม่แก้ของเดิม)
3. **ห้ามแตะระบบ auth** (`DASHBOARD_USER/PASS`, session cookie, localhost guard)
4. **ห้ามแตะ `frontend/vendor/`** (ไลบรารี) — ห้ามเปลี่ยนไปใช้ CDN เฉพาะหน้า (กัน CDN ล่ม)
5. **ห้าม hard-code ค่าลับ/IP** ลง frontend — ค่าลับอยู่ที่ .env ของ backend เท่านั้น
6. แก้เฉพาะหน้าตา/เลย์เอาต์/UX — ยึด brief ใน `frontend/design/`

## ข้อจำกัดทางเทคนิคที่ต้องรู้

- `index.html` โหลด `/static/vendor/*` — ตัว API เสิร์ฟ `frontend/` เป็น static อยู่แล้ว
- Dashboard บังคับ login ผ่าน session cookie (basic auth สำหรับ API/curl)
- VPS เล็ก (1 vCPU/1GB) — อย่าเพิ่มโหลด client ที่ poll ถี่/หนัก
- หากแก้ไฟล์ frontend ใหญ่ ให้แตก `index.html` ทีละส่วนด้วยการเพิ่มไฟล์ใหม่
  (อย่าทำ "จัดใหม่ทั้งหมด" ใน PR เดียว)