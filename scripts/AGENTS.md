# scripts/ — สคริปต์เสริม (ไม่อยู่ใน path ของระบบ live)

## โฟลเดอร์นี้ทำอะไร

| โฟลเดอร์ | ทำอะไร |
|---|---|
| `diagnostics/` | เช็คการเชื่อมต่อ/symbol/setup (test_connection, check_symbols ฯลฯ) |
| `data_tools/` | backfill ข้อมูลย้อนหลังเป็น CSV (fetch_history_paginated ฯลฯ) |
| `backtest/` | ชุด backtest legacy Phase-1 (run_backtest, setup_backtest ฯลฯ) — แก้น้อยที่สุด |

## ไฟล์สำคัญ

- `diagnostics/test_connection.py` — เช็ค Deriv WS ทีละชั้น (TLS → WS → library)
- `backtest/setup_backtest.py` — backtest กลยุทธ์ Rule-Based (import backend.indicators ได้)

## ข้อควรระวัง

- ระบบ live **ไม่ import** โฟลเดอร์นี้ — แก้พังก็ไม่กระทบการเทรด แต่ห้ามใช้ sys.path.insert ลอยๆ
- backtest ใช้ CSV ใหญ่ใน `data/` (git-ignored) — อย่า commit ไฟล์ CSV
