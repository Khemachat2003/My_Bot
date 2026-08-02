"""
check_symbols.py — เครื่องมือ diagnostic: ดึงรายชื่อ active_symbols จาก Deriv API
เพื่อเช็คว่าสัญลักษณ์ปัจจุบัน (DERIV_SYMBOL ใน .env หรือ frxXAUUSD ค่า default)
ใช้งานได้จริงบน app_id/บัญชีนี้หรือไม่ — ใช้ตอนเจอ error "Symbol ... is invalid"

หมายเหตุสำคัญ: frxXAUUSD คือราคาทองจริง ตลาดปิดวันเสาร์-อาทิตย์ (และนอกเวลาเปิดตลาด
Forex ปกติ) ช่วงตลาดปิด Deriv จะไม่ list สัญลักษณ์นี้ใน active_symbols และปฏิเสธการ
subscribe ราคาสด แม้ ticks_history (ข้อมูลย้อนหลังที่บันทึกไว้แล้ว) จะยังดึงได้ปกติ —
ถ้าต้องการทดสอบระบบได้ตลอด 24/7 ให้ตั้ง DERIV_SYMBOL=R_100 (หรือ synthetic
index อื่นๆ ของ Deriv) ใน .env ชั่วคราว

รัน:
    python -m backend.check_symbols
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import websocket

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from backend.deriv_feed import DERIV_WS_URL, DEFAULT_SYMBOL

TARGET_SYMBOL = os.getenv("DERIV_SYMBOL", DEFAULT_SYMBOL)


def fetch_active_symbols() -> tuple[list[dict], dict]:
    ws = websocket.create_connection(DERIV_WS_URL, timeout=15)
    ws.send(json.dumps({"active_symbols": "brief"}))
    raw = ws.recv()
    ws.close()
    data = json.loads(raw)
    return data.get("active_symbols", []), data


def main():
    print(f"[check_symbols] กำลังดึง active_symbols จาก {DERIV_WS_URL} ...")
    print(f"[check_symbols] กำลังเช็คสัญลักษณ์เป้าหมาย: '{TARGET_SYMBOL}' "
          f"(ตั้งค่าผ่าน DERIV_SYMBOL ใน .env ได้)\n")

    symbols, raw_response = fetch_active_symbols()

    if raw_response.get("error"):
        print(f"❌ Deriv ตอบ error: {raw_response['error']}")
        return

    print(f"[check_symbols] พบทั้งหมด {len(symbols)} สัญลักษณ์")

    if not symbols:
        print(
            "\n⚠️ ได้ 0 สัญลักษณ์กลับมา — เกิดได้จาก 2 กรณีหลัก:\n"
            "  1) ตลาดปิดทั้งหมดตอนนี้ (เช่น วันเสาร์-อาทิตย์) และ app_id/บัญชีนี้\n"
            "     กรองเฉพาะสัญลักษณ์ที่ 'เปิดซื้อขายอยู่จริง' เท่านั้น\n"
            "  2) request ถูก reject แบบไม่มี error field ชัดเจน\n"
            f"\nRaw response keys จาก Deriv: {list(raw_response.keys())}\n"
            "ลองรันคำสั่งนี้อีกครั้งในวันธรรมดา (จันทร์-ศุกร์) ระหว่างตลาด Forex เปิด "
            "เพื่อเช็คว่า frxXAUUSD กลับมาหรือไม่ หรือทดสอบระบบด้วย synthetic index "
            "ตอนนี้เลยโดยตั้ง DERIV_SYMBOL=R_100 ใน .env (เทรดได้ตลอด 24/7 ไม่มีวันหยุด)"
        )
        return

    exact = [s for s in symbols if s.get("symbol") == TARGET_SYMBOL]
    if exact:
        s = exact[0]
        print(f"✅ '{TARGET_SYMBOL}' มีอยู่จริงและเทรดได้ตอนนี้: "
              f"{s.get('display_name')} (market={s.get('market')}, "
              f"submarket={s.get('submarket')})")
    else:
        print(f"❌ ไม่พบ '{TARGET_SYMBOL}' ในรายการ active_symbols ที่เปิดอยู่ตอนนี้ "
              f"(อาจเป็นเพราะตลาดปิดอยู่ตอนนี้)")

    gold_like = [
        s for s in symbols
        if "xau" in s.get("symbol", "").lower() or "gold" in s.get("display_name", "").lower()
    ]
    print("\nสัญลักษณ์ที่เกี่ยวกับ Gold/XAU ที่เปิดซื้อขายอยู่ตอนนี้:")
    if not gold_like:
        print("  (ไม่พบเลยตอนนี้ — น่าจะเป็นเพราะตลาดทองปิดอยู่ ไม่ใช่เพราะบัญชีไม่มีสิทธิ์)")
    for s in gold_like:
        print(f"  - {s.get('symbol')}  |  {s.get('display_name')}  "
              f"(market={s.get('market')}/{s.get('submarket')})")

    synthetic_like = [
        s for s in symbols
        if s.get("market") == "synthetic_index"
    ][:8]
    if synthetic_like:
        print("\nตัวอย่าง synthetic/OTC index ที่เทรดได้ตลอด 24/7 (ใช้ทดสอบระบบตอนตลาดจริงปิด):")
        for s in synthetic_like:
            print(f"  - {s.get('symbol')}  |  {s.get('display_name')}")


if __name__ == "__main__":
    main()
