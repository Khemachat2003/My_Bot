"""
telegram.py — ฟังก์ชันส่งข้อความแจ้งเตือนเข้า Telegram ใช้ร่วมกันทั้ง 2 ระบบ
(Rule-Based Setup Engine และ ML Model Engine) เพื่อไม่ให้ต้องเขียนโค้ดส่งซ้ำ 2 ที่

ตั้งค่าใน .env (ดู .env.example):
    TELEGRAM_BOT_TOKEN=xxxxxxxxxx
    TELEGRAM_CHAT_ID=xxxxxxxxxx

ถ้าไม่ได้ตั้งค่า จะ fallback เป็น print ออก console แทน (สะดวกตอน dev/localhost)

v2 (แก้บั๊ก "Telegram ไม่เคยขึ้น"):
  - reload env ทุกครั้งที่ส่ง (กันแก้ .env แล้วลืม restart process)
  - retry อัตโนมัติ 3 ครั้ง (network/5xx)
  - log รายละเอียด HTTP status + response body ชัดเจน (401 = token ผิด,
    400 chat not found = chat_id ผิด) — เดิม error ถูกกลืนเงียบ
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent

_TELEGRAM_API = "https://api.telegram.org"


def _get_config() -> tuple[str | None, str | None]:
    """อ่าน env สดทุกครั้ง (ไม่ cache ไว้ที่ module level) — load_dotenv
    ไม่ทับ env ของ process (compose env_file) เพราะ override=False โดยค่าเริ่มต้น"""
    load_dotenv(ROOT_DIR / ".env", override=False)
    return os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message: str, retries: int = 3) -> bool:
    """ส่งข้อความเข้า Telegram; คืน True/False ว่าส่งสำเร็จหรือไม่
    (ถ้าไม่ได้ตั้งค่า TOKEN/CHAT_ID จะ print ออก console แทนและคืน False)"""
    bot_token, chat_id = _get_config()
    if not bot_token or not chat_id:
        print(f"\n[Telegram - DEV MODE, ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN/CHAT_ID ใน .env]\n{message}\n")
        return False

    import requests
    url = f"{_TELEGRAM_API}/bot{bot_token}/sendMessage"
    last_err: str = ""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "text": message},
                timeout=15,
            )
            body = resp.text[:300]
            if resp.status_code == 200:
                return True
            # 401 = token ผิด / 400 = chat_id ผิด → retry ก็ไม่มีประโยชน์
            if resp.status_code in (400, 401, 403, 404):
                print(f"[Telegram] FAIL status={resp.status_code} (ไม่ retry): {body}")
                return False
            last_err = f"status={resp.status_code} {body}"
            print(f"[Telegram] พยายาม {attempt}/{retries} ไม่สำเร็จ ({last_err}) — retry...")
        except requests.exceptions.Timeout:
            last_err = "timeout 15s"
            print(f"[Telegram] พยายาม {attempt}/{retries} timeout — retry...")
        except Exception as e:
            last_err = str(e)
            print(f"[Telegram] พยายาม {attempt}/{retries} error: {e} — retry...")
        if attempt < retries:
            time.sleep(2 * attempt)
    print(f"[Telegram] ส่งข้อความไม่สำเร็จ (หมด {retries} ครั้ง): {last_err}\n{message}")
    return False


def send_telegram_document(file_path, caption: str = "") -> bool:
    """ส่งไฟล์ (เช่น backup zip) เข้า Telegram ผ่าน sendDocument
    คืน True/False ว่าส่งสำเร็จหรือไม่"""
    bot_token, chat_id = _get_config()
    if not bot_token or not chat_id:
        print(f"\n[Telegram - DEV MODE, ยังไม่ได้ตั้งค่า .env] (จะส่งไฟล์ {file_path})\n{caption}\n")
        return False
    try:
        import requests
        url = f"{_TELEGRAM_API}/bot{bot_token}/sendDocument"
        fname = str(file_path).replace("\\", "/").rsplit("/", 1)[-1]
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (fname, f)},
                timeout=120,
            )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Telegram] ส่งไฟล์ไม่สำเร็จ: {e} ({file_path})")
        return False
