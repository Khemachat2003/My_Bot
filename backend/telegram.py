"""
telegram.py — ฟังก์ชันส่งข้อความแจ้งเตือนเข้า Telegram ใช้ร่วมกันทั้ง 2 ระบบ
(Rule-Based Setup Engine และ ML Model Engine) เพื่อไม่ให้ต้องเขียนโค้ดส่งซ้ำ 2 ที่

ตั้งค่าใน .env (ดู .env.example):
    TELEGRAM_BOT_TOKEN=xxxxxxxxxx
    TELEGRAM_CHAT_ID=xxxxxxxxxx

ถ้าไม่ได้ตั้งค่า จะ fallback เป็น print ออก console แทน (สะดวกตอน dev/localhost)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage" if BOT_TOKEN else None


def send_telegram(message: str) -> bool:
    """ส่งข้อความเข้า Telegram; คืน True/False ว่าส่งสำเร็จหรือไม่
    (ถ้าไม่ได้ตั้งค่า TOKEN/CHAT_ID จะ print ออก console แทนและคืน False)"""
    if not BOT_TOKEN or not CHAT_ID:
        print(f"\n[Telegram - DEV MODE, ยังไม่ได้ตั้งค่า .env]\n{message}\n")
        return False
    try:
        import requests
        resp = requests.post(
            _API_URL,
            data={"chat_id": CHAT_ID, "text": message},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Telegram] ส่งข้อความไม่สำเร็จ: {e}\n{message}")
        return False


def send_telegram_document(file_path, caption: str = "") -> bool:
    """ส่งไฟล์ (เช่น backup zip) เข้า Telegram ผ่าน sendDocument
    คืน True/False ว่าส่งสำเร็จหรือไม่"""
    if not BOT_TOKEN or not CHAT_ID:
        print(f"\n[Telegram - DEV MODE, ยังไม่ได้ตั้งค่า .env] (จะส่งไฟล์ {file_path})\n{caption}\n")
        return False
    try:
        import requests
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        fname = str(file_path).replace("\\", "/").rsplit("/", 1)[-1]
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                data={"chat_id": CHAT_ID, "caption": caption},
                files={"document": (fname, f)},
                timeout=120,
            )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Telegram] ส่งไฟล์ไม่สำเร็จ: {e} ({file_path})")
        return False
