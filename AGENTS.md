# AGENTS.md — คู่มือนำทางสำหรับ AI agent (และมนุษย์)

## โปรเจกต์คืออะไร

- ระบบเทรดทอง XAUUSD: สัญญาณ 2 เครื่องยนต์ — Rule-Based 11-Checklist (`setup_feed`/`setup_scorer`)
  + ML LightGBM (`ml_forecaster`/`notifier`) → ส่ง Telegram, แสดงบน Dashboard, ส่งออเดอร์ MT5
- รันทุกระบบด้วย supervisor เดียว: `python run_live.py` (auto-restart) · Dashboard: `http://localhost:8000`
- Login dashboard / keys ทั้งหมดอยู่ใน `.env` (เริ่มจาก `.env.example`) — ห้าม hard-code ทุกชนิด

## โครงสร้างโฟลเดอร์

| โฟลเดอร์ | ทำอะไร | คู่มือย่อย |
|---|---|---|
| `backend/` | เครื่องยนต์สัญญาณ + API (FastAPI) + SQLite | `backend/AGENTS.md` |
| `frontend/` | Dashboard SPA (Vite → build เป็น `dist/`) | `frontend/AGENTS.md` |
| `executor/` | MT5 order executor (Windows, รันแยกเครื่อง) | `executor/AGENTS.md` |
| `scripts/` | วินิจฉัย / เครื่องมือข้อมูล / backtest legacy | `scripts/AGENTS.md` |
| `tests/` | pytest (characterization + หน้าเว็บ build) | - |
| `docs/` | เอกสารระบบ + แผน + code_map/api_contract | - |
| `deploy/`, `docker-compose.yml`, `.github/workflows/` | ของ VPS (deploy อัตโนมัติเมื่อ push main) | - |
| `_archive/` | ไฟล์เก่า/ตาย ยังไม่ลบ (รวม index.legacy.html) | - |

## คำสั่งสำคัญ

```bash
./venv/Scripts/python.exe -m pytest -q      # เทสต์ทั้งหมด (65 ต้องผ่าน — มี pre-commit hook บังคับอยู่แล้ว)
./venv/Scripts/python.exe -m ruff check backend   # lint python
python run_live.py                          # รันระบบจริง (api + setup_feed + notifier + ...)
# frontend (ต้อง npm install ครั้งแรก):
cd frontend && npm run check                # lint + typecheck + unit test + build
cd frontend && npm run dev                  # dev server (API จาก uvicorn :8000 ที่ต้องรันคู่)
cd frontend && npm run build                # build → dist/ (แล้ว commit dist — ดูกฎด้านล่าง)
cd frontend && npm run test:visual          # ภาพ + network ต้องตรง baseline
```

## กฎเหล็ก (ห้ามละเมิด)

1. **ห้ามแตะ `executor/`** และ logic การเทรด/คำนวณ/ส่งสัญญาณ — `setup_scorer.py`, `setup_feed.py`,
   `notifier.py`, `indicators.py` ถ้าต้องแตะ หยุดแล้วถามผู้ใช้ก่อนเสมอ
2. **ห้าม push main** — push main = auto-deploy ขึ้น VPS จริง ทำงานบน branch เท่านั้น
3. **ห้ามใส่ความลับในโค้ด** — token/รหัสผ่าน/IP อยู่ที่ `.env` เท่านั้น (รวมถึงไฟล์ test/fixture)
4. **ห้ามอ่านไฟล์ใหญ่ทั้งไฟล์** (`db.py`, `api.py`, `index.html` เก่า) — ใช้ grep/outline
   แล้วอ่านเฉพาะช่วงที่ต้องการ ดูจุดแก้ที่ต้องการจาก `docs/code_map.md` ก่อน
5. **ห้ามเปลี่ยน shape/response ของ `/api/*` เดิม** — ต้องเพิ่มได้ต่อท้ายเท่านั้น (ดู `docs/api_contract.md`)
6. **`frontend/dist/` ต้อง commit** เพราะ VPS ไม่มี Node — แก้ `src/**` แล้วต้อง `npm run build` ใหม่ทุกครั้ง
7. Commit เล็ก ข้อความชัด รัน pytest ผ่านก่อน commit (pre-commit hook จะบล็อกให้เอง)

## อยากแก้อะไร → ไปที่ไหน

ดูตารางเต็มใน `docs/code_map.md` — ตัวอย่าง:

| อยากแก้ | ไปที่ไฟล์ | เกี่ยวข้อง |
|---|---|---|
| สี/ธีมหน้าเว็บ | `frontend/src/styles/tokens.css` | build ใหม่ + commit dist |
| การ์ดสัญญาณ / ตาราง | `frontend/src/features/*/` | `GET /api/*` (code_map) |
| endpoint ใหม่ | `backend/api.py` (→ Phase B แยกเป็น routes) | เทสต์ + api_contract |
| สูตรเทรด/R:R | `executor/…`, `backend/setup_scorer.py` | **ห้ามแตะโดยไม่ถาม** |

## เมื่อไรต้องถามผู้ใช้ก่อน

- แตะ logic การเทรด/การคำนวณ/การส่งสัญญาณ (ข้อ 1)
- เพิ่ม library/dependency ใหม่ทั้ง Python และ npm
- เปลี่ยน deploy pipeline / docker-compose / auth ของ dashboard
- ลบไฟล์ใน `_archive/`
