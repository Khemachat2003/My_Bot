# แผนการจัดโครงสร้างใหม่ (restructure plan) — สิ่งที่ทำแล้ว

> Branch: `refactor/project-structure` — หลักการ: **ย้ายไฟล์ + แก้ path/import พร้อมกัน
> ใน commit เดียว + รันเทสต์ทุกครั้ง** เพื่อให้ทุก commit deploy ได้เสมอ

## โครงสร้างใหม่ที่ตั้งเป้า

```
xauusd-bot/
├── run_live.py             ← จุดเริ่มระบบ (คงที่)
├── backend/                ← ระบบหลัก (เรียกผ่าน -m backend.X — paths คงเดิมทั้งหมด)
├── executor/               ← MT5 executor (Windows, รันแยกเครื่อง)
├── frontend/
│   ├── index.html          ← dashboard หลัก (คงที่)
│   ├── vendor/             ← ไลบรารีในเครื่อง (คงที่)
│   ├── demos/              ← ไฟล์ demo กราฟ standalone
│   └── design/             ← design briefs
├── scripts/
│   ├── diagnostics/        ← สคริปต์เช็คการเชื่อมต่อ/symbol/setup
│   ├── data_tools/         ← เครื่องมือข้อมูล (backfill ฯลฯ)
│   └── backtest/           ← ชุด backtest legacy Phase-1
├── tests/                  ← pytest (คงที่)
├── docs/                   ← เอกสารระบบ + แผน
├── deploy/                 ← systemd/nginx/firewall (คงที่)
└── _archive/               ← ไฟล์เก่า/พัง ยังไม่ลบ
```

## ตารางย้ายไฟล์ — สิ่งที่ทำแล้ว

| ไฟล์เดิม | ตำแหน่งใหม่ | การแก้ที่ตามไป | commit |
|---|---|---|---|
| `check_setup.py` | `scripts/diagnostics/check_setup.py` | อัปเดต docstring | `1dacdef` |
| `backend/check_symbols.py` | `scripts/diagnostics/check_symbols.py` | อัปเดต docstring | `1dacdef` |
| `scripts/test_connection.py` | `scripts/diagnostics/test_connection.py` | อัปเดต docstring | `1dacdef` |
| `scripts/test_ws_handshake.py` | `scripts/diagnostics/test_ws_handshake.py` | อัปเดต docstring | `1dacdef` |
| `check_symbols.py` (root ซ้ำ) | `_archive/check_symbols_root_duplicate.py` | หมายเหตุหัวไฟล์ | `1dacdef` |
| `backfill_ema200.py` | `scripts/data_tools/backfill_ema200.py` | **แก้ ROOT** `.parent.parent.parent` | `0d3ee6c` |
| `fetch_history_paginated.py` | `scripts/data_tools/fetch_history_paginated.py` | อัปเดต docstring | `0d3ee6c` |
| `backend/backtest.py` | `scripts/backtest/backtest.py` | **แก้ import** → `backend.indicators` + sys.path root | `0652587` |
| `backend/strategies.py` | `scripts/backtest/strategies.py` | (standalone) | `0652587` |
| `backend/data_fetcher.py` | `scripts/backtest/data_fetcher.py` | **แก้ DATA_DIR** → parents[2] | `0652587` |
| `backend/report.py` | `scripts/backtest/report.py` | **แก้ import + REPORT_DIR** | `0652587` |
| `run_backtest.py` | `scripts/backtest/run_backtest.py` | **แก้ import ทั้งชุด** | `0652587` |
| `setup_backtest.py` | `scripts/backtest/setup_backtest.py` | (self-locating อยู่แล้ว) | `0652587` |
| `mt5_executor.py` | `executor/mt5_executor.py` | **แก้ ROOT** `.parent.parent` + `executor/__init__.py` + เทสต์ import | `b63421c` |
| `frontend/*-demo.html` (4) | `frontend/demos/` | (ใช้ CDN จึงย้ายปลอดภัย) + README กำกับ | `c71903d` |
| `frontend/*-brief.md` (3) | `frontend/design/` | README กำกับ | `c71903d` |
| `backend/ml_forecaster/confluence.py` | `_archive/ml_forecaster_confluence_broken_import.py` | import พัง+ไม่มีใครเรียก + หมายเหตุ | `7279eb8` |
| `Setup101.txt` | `docs/strategy_setup_notes.md` | (โน้ตกลยุทธ์) | `7279eb8` |

## งานความปลอดภัยที่ทำพร้อมกัน

| งาน | commit |
|---|---|
| ถอน IP/user/pass hardcode จาก `validate_gate_real.py` (ต้องอ่าน .env) | `2e64db2` |
| แทน IP/user/pass ใน `DEPLOY.md` ด้วย placeholder | `2e64db2` |

## หลักการที่ยึด

1. **Paths ของระบบ live คงเดิมทั้งหมด** — `backend.*` เรียกผ่าน `-m backend.X` เหมือนเดิม
2. **ย้าย + แก้ import + เทสต์ ใน commit เดียว** — ทุก commit deploy ได้
3. **ไฟล์ research/replay ไม่แตะระบบ live** — ตัว live รู้จักผ่าน API เท่านั้น
4. **ห้ามใช้ sys.path.insert(0, parent) แบบลอยๆ** — ต้องคำนวณ root ชัดเจน + comment อธิบาย
5. **เทสต์ 63 เคสต้องผ่านทุกครั้งก่อน commit**
