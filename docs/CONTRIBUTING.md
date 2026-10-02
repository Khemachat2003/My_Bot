# CONTRIBUTING — กฎการพัฒนาโปรเจกต์นี้

## โครงสร้างโฟลเดอร์ — วางไฟล์ที่ใหม่ไว้ที่ไหน

| ประเภทงาน | ที่ที่ถูกต้อง |
|---|---|
| ระบบ live หลัก (engine/DB/API) | `backend/` เท่านั้น — เรียกผ่าน `python -m backend.<ชื่อ>` |
| ออเดอร์ MT5 / โค้ดเครื่อง Windows | `executor/` |
| สคริปต์เช็คการเชื่อมต่อ / เครื่องมือโดดๆ | `scripts/diagnostics/`, `scripts/data_tools/` |
| ชุด backtest legacy Phase-1 | `scripts/backtest/` |
| เอกสารทุกชนิด | `docs/` |
| ไฟล์ demo กราฟ standalone | `frontend/demos/` |
| ไฟล์ไม่ใช้แล้ว (ยังไม่ลบ) | `_archive/` |

**ห้าม:** วางไฟล์ .py ใหม่ที่ root · เขียน sys.path hack แบบลอยๆ · import ระบบ live
จาก `scripts/` กลับมาที่ `backend/` (ต่อกันผ่าน API เท่านั้น)

## กฎตั้งชื่อ

- Python: `snake_case` ทุกไฟล์/ตัวแปร/ฟังก์ชัน ชื่อต้องบอกหน้าที่ (`signal_dispatcher`, `risk_calculator`)
- Frontend JS/CSS: `camelCase` / `kebab-case`
- ห้ามชื่อกำกวม: `utils2.py`, `new.py`, `final.py`, `test123.py`
- ฟังก์ชันสำคัญต้องมี docstring อธิบาย **ทำไม** (เหตุผลธุรกิจ/เทคนิค) ไม่ใช่แค่ทำอะไร

## วิธีเพิ่มกลยุทธ์ใหม่

1. สร้างตัว scoring เป็น **pure function** รับ DataFrame → คืนผล (`SetupResult`-like)
2. เขียน characterization tests ครอบก่อน (`tests/test_<ชื่อ>.py`) — ดูตัวอย่าง `tests/test_setup_scorer.py`
3. ฝั่ง live ที่ดึงมาใช้เป็นแค่ **thin wrapper** (`setup_feed`-like) ห้ามฝังตรรกะใน wrapper
4. ตั้งค่า/น้ำหนักใส่ `backend/setup_config.json` — ห้าม hard-code ในโค้ด

## วิธีเพิ่ม integration ใหม่ (broker/feed อื่น)

1. สร้างไฟล์ใหม่ใน `backend/data_feed/` — ทำตามหน้าที่เดียวกับ `deriv_feed.py`
2. ซ่อนหลัง **interface เดียวกัน** (ฟังก์ชันสร้าง OHLC DataFrame)
3. สลับได้ผ่าน `.env` (เช่น `DERIV_SYMBOL` สลับ) — ห้ามแก้ caller
4. การส่งแจ้งเตือนใช้ `backend/telegram.py` ตัวกลางเดียว — ห้ามเขียนส่งซ้ำ

## Commit convention (ตาม DEPLOY.md)

```
ประเภท(ส่วนที่แก้): อธิบายสั้นๆ ว่าอะไรพังและแก้ยังไง
fix(...), feat(...), chore(...), refactor(...), docs(...)
```

## ก่อน commit ทุกครั้ง

1. `./venv/Scripts/python.exe -m pytest` → ต้องผ่านทั้งหมด
2. `./venv/Scripts/python.exe -m ruff check <ไฟล์ที่แก้>`
3. `git status` — ไม่มีไฟล์แปลกปลอม (`.env`/`data/`/`mt5_state.db` ห้ามขึ้น)
4. pre-commit hook เปิดไว้: `python -m pre-commit install`
5. **ห้าม push ตรง `main` โดยไม่ผ่านการตรวจ** — `main` = production (auto-deploy VPS)

## ความลับ

- ค่าลับทุกชนิด (token/รหัสผ่าน/IP ภายใน) มาจาก `.env` เท่านั้น — ห้าม hard-code
- เพิ่มตัวแปรใหม่ → อัปเดต `.env.example` พร้อมคำอธิบายทุกบรรทัด