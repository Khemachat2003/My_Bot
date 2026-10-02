# executor/ — MT5 order executor (Windows)

## โฟลเดอร์นี้ทำอะไร

รันบนเครื่อง Windows ที่เปิด MetaTrader5 (แยกจาก VPS): poll สัญญาณจาก API ของ dashboard
แล้วส่งออเดอร์จริงพร้อม SL/TP (fractal + R:R) — ตั้งค่าผ่าน `.env` (MT5_*)

## ไฟล์สำคัญ

- `mt5_executor.py` — ตัวเดียวของโฟลเดอร์ (จุดเริ่ม: `python executor/mt5_executor.py --dry-run`)

## ⛔ ข้อควรระวัง

- **ห้ามแก้ logic ในไฟล์นี้โดยไม่ถามผู้ใช้ก่อนทุกครั้ง** (ความเสี่ยงเงินจริง — บังคับโดย AGENTS.md root)
- เขียน `mt5_state.db` ที่ root ของโปรเจกต์ — อย่า commit
- ระบบ live บน VPS ไม่รู้จักโฟลเดอร์นี้ — คุยกันผ่าน HTTP API เท่านั้น
