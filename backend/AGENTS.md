# backend/ — เครื่องยนต์สัญญาณ + API + ฐานข้อมูล

## โฟลเดอร์นี้ทำอะไร

| กลุ่ม | ไฟล์ | หน้าที่ |
|---|---|---|
| เครื่องยนต์สัญญาณ | `setup_feed.py`, `setup_scorer.py`, `notifier.py`, `ml_forecaster/` | 🔵 Rule-Based + 🟢 ML → เขียน `setup_signals`/`ml_signals` + Telegram |
| API dashboard | `api.py` | FastAPI: เสิร์ฟหน้าเว็บ + `/api/*` ทั้งหมด + auth |
| ฐานข้อมูล | `db.py`, `setup_db.py` | SQLite WAL (data/bot.db) — ตารางกลาง/ฝั่ง Setup |
| โครงสร้างรอง | `data_feed/`, `market_hours.py`, `telegram.py`, `macro_feed.py`, `backup.py`, `indicators.py` | ข้อมูลราคา/เวลาตลาด/แจ้งเตือน/สำรอง/อินดิเคเตอร์ |

## ⛔ ข้อควรระวัง

- `setup_scorer.py` / `setup_feed.py` / `notifier.py` / `indicators.py` = logic การเทรด —
  **ห้ามแตะโดยไม่ถามผู้ใช้** (มี characterization tests ครอบ 63 เคส ต้องผ่านทุกครั้ง)
- รูปแบบ response ของ `/api/*` เดิมห้ามเปลี่ยน (ดู `docs/api_contract.md`)
- ทุก timestamp เป็น UTC · ไฟล์ใหญ่ (`db.py` ~1,400 บรรทัด, `api.py` ~840 บรรทัด) —
  **อ่านเป็นช่วง + grep เท่านั้น ห้าม cat ทั้งไฟล์** ดูจุดแก้ที่ `docs/code_map.md`
- ระบบรันหลาย process บน SQLite ไฟล์เดียว (WAL) — อย่าเปลี่ยนรูปแบบการเปิด connection ใน `db.py`
