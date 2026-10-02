# Runbook — เริ่ม/หยุด/ตรวจสุขภาพระบบ

> คำสั่งทั้งหมดรันจาก root ของโปรเจกต์ บน VPS (Linux)

## เริ่มระบบ

```bash
# วิธีที่ 1 — Docker (deploy ปกติ, อ่าน DEPLOY.md)
docker compose up -d --build

# วิธีที่ 2 — systemd (host process)
sudo systemctl start xauusd-bot

# วิธีที่ 3 — รันตรงๆ (ทดสอบ)
./venv/Scripts/python.exe run_live.py        # Windows
./venv/bin/python run_live.py                # Linux
```

## หยุดระบบ

```bash
docker compose down               # Docker
sudo systemctl stop xauusd-bot    # systemd
```

## ตรวจสุขภาพ (จากในเครื่อง VPS)

```bash
curl -s -u "$DASHBOARD_USER:$DASHBOARD_PASS" http://127.0.0.1:8000/api/health  # API ตอบไหม
docker compose ps                     # supervisor ครบไหม
docker compose logs --tail 50 setup_feed   # ตัว feed ผิดพลาดล่าสุด
```

- ครบ 5 supervisor: setup_feed / notifier / api / macro_feed / backup (ดู `docker compose ps`)

## สัญญาณว่าระบบกำลังทำงานถูกต้อง

1. `data/bot.db` มีแถวใหม่ใน `setup_signals` ตามรอบตลาด (M1/M5)
2. Dashboard login ได้ + กราฟวิ่ง (Deriv feed ตอบ)
3. Telegram ได้รับแจ้งเมื่อมีสัญญาณ FIRE ใหม่
4. `executor/mt5_executor.py` (เครื่อง Windows) มี log รับสัญญาณเมื่อมี FIRE

## ปัญหาที่พบบ่อย

| อาการ | เช็ค | แก้ |
|---|---|---|
| Deriv feed หลุดวน reconnect | `docker compose logs deriv_feed` | ดู `scripts/diagnostics/test_connection.py` / firewall |
| API 401 จากภายนอก | .env DASHBOARD_USER/PASS ยังเป็นค่าเริ่มต้น | ตั้งค่าใหม่ (ระบบบล็อกภายนอกเมื่อใช้ค่าเริ่มต้น) |
| ไม่มีสัญญาณใหม่ | ตลาดปิด? เช็ค `scripts/diagnostics/check_setup.py` | รอตลาดเปิด (ดู market_hours.py) |
| MT5 ไม่ส่งออเดอร์ | บัญชี demo login? `--dry-run` ได้ไหม | ดู log executor + เช็ค MT5 terminal |
| เทลีแกรมไม่ส่ง | ดู `telegram_log` ตาราง | token/chat id ใน .env |

## Backup

- `backend/backup.py` รันอัตโนมัติใน run_live → ไฟล์ที่ `backups/`
- Restore: หยุด supervisor → แทน `data/bot.db` ด้วยไฟล์ backup → เริ่มใหม่
