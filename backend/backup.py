"""
backup.py — สำรองข้อมูลอัตโนมัติ (DB + models + candles) เข้า Telegram
=====================================================================================
รันเป็น thread ใน run_live.py:
  - ครั้งแรกตอน bot สตาร์ต (delay ไม่กี่วิ เพื่อให้ DB พร้อม)
  - แล้วซ้ำทุก BACKUP_INTERVAL_HOURS ชั่วโมง (default 6)

สิ่งที่สำรอง (zip ทั้งหมดเข้าไฟล์เดียว):
  - data/bot.db  (journal, registry, stats, สัญญาณ)
  - backend/ml_forecaster/*.joblib  (โมเดล ML)
  - data/*.csv   (candle history ต่าง ๆ)

ตั้งค่าใน .env (ดู .env.example):
    BACKUP_ENABLED=true
    BACKUP_INTERVAL_HOURS=6
    BACKUP_KEEP_LOCAL=10     (เก็บไฟล์ zip เก่าไว้กี่อันใน data/backups/)
"""
from __future__ import annotations

import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

from backend.telegram import send_telegram_document

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "backend" / "ml_forecaster"
BACKUP_DIR = DATA_DIR / "backups"

INTERVAL_HOURS = float(os.getenv("BACKUP_INTERVAL_HOURS", "6"))
KEEP_LOCAL = int(os.getenv("BACKUP_KEEP_LOCAL", "10"))
FIRST_DELAY_SEC = 10


def _collect_files() -> list[tuple[Path, str]]:
    """รวบรวมไฟล์ที่จะสำรอง → [(เส้นทางจริง, ชื่อใน zip)]"""
    files: list[tuple[Path, str]] = []

    db_path = DATA_DIR / "bot.db"
    if db_path.exists():
        files.append((db_path, "bot.db"))

    for f in sorted(MODELS_DIR.glob("*.joblib")):
        files.append((f, f"models/{f.name}"))

    for f in sorted(DATA_DIR.glob("*.csv")):
        files.append((f, f"data/{f.name}"))

    return files


def create_backup() -> Path | None:
    """สร้างไฟล์ zip backup ที่ data/backups/xauusd_YYYYMMDD_HHMMSS.zip
    คืน Path ของไฟล์ที่สร้าง (หรือ None ถ้าไม่มีอะไรจะสำรอง)"""
    files = _collect_files()
    if not files:
        print("[Backup] ไม่พบไฟล์ที่จะสำรอง (data/bot.db หาย?)")
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = BACKUP_DIR / f"xauusd_{stamp}.zip"

    total = 0
    try:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for real_path, arcname in files:
                zf.write(real_path, arcname)
                total += real_path.stat().st_size
    except Exception as e:
        print(f"[Backup] สร้าง zip ไม่สำเร็จ: {e}")
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None

    print(f"[Backup] สร้าง {out_path.name} ({total / 1e6:.1f} MB, {len(files)} ไฟล์)")
    _prune_old_backups()
    return out_path


def _prune_old_backups():
    """ลบไฟล์ zip เก่าเกิน KEEP_LOCAL ไฟล์ (เก็บเฉพาะล่าสุด)"""
    try:
        zips = sorted(BACKUP_DIR.glob("xauusd_*.zip"), key=lambda p: p.stat().st_mtime)
        for old in zips[:-KEEP_LOCAL]:
            old.unlink(missing_ok=True)
            print(f"[Backup] ลบ backup เก่า: {old.name}")
    except Exception as e:
        print(f"[Backup] prune ไม่สำเร็จ: {e}")


def run_backup_once() -> bool:
    """สร้าง zip แล้วส่งเข้า Telegram; คืน True ถ้าทั้งคู่สำเร็จ"""
    zip_path = create_backup()
    if zip_path is None:
        return False
    size_mb = zip_path.stat().st_size / 1e6
    caption = (
        f"📦 [BACKUP] XAUUSD Bot\n"
        f"ไฟล์: {zip_path.name}\n"
        f"ขนาด: {size_mb:.2f} MB\n"
        f"เวลา: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"ประกอบด้วย: bot.db + models + candles"
    )
    return send_telegram_document(zip_path, caption)


def backup_loop(stop_event) -> None:
    """thread หลัก: backup ตอนเริ่ม + รอทุก INTERVAL_HOURS"""
    # รอสักครู่หลัง bot สตาร์ต ให้ DB สร้าง/พร้อมก่อน
    deadline = time.time() + FIRST_DELAY_SEC
    while time.time() < deadline:
        if stop_event.wait(min(1.0, max(0, deadline - time.time()))):
            return

    while not stop_event.is_set():
        try:
            ok = run_backup_once()
            if ok:
                print(f"[Backup] ส่งเข้า Telegram สำเร็จ — รอบถัดไปใน {INTERVAL_HOURS:g} ชม.")
            else:
                print("[Backup] ส่งไม่สำเร็จ (ยังไม่มี TELEGRAM config หรือไฟล์?) — ลองใหม่รอบหน้า")
        except Exception as e:
            print(f"[Backup] error: {e}")
        try:
            stop_event.wait(INTERVAL_HOURS * 3600)
        except Exception:
            pass
