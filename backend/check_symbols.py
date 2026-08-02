"""
check_symbols.py — เครื่องมือ diagnostic: ดึงรายชื่อ active_symbols จาก Deriv API
เพื่อเช็คว่าสัญลักษณ์ "frxXAUUSD" (หรือชื่ออื่นที่เกี่ยวกับ Gold/XAU) ใช้งานได้จริง
บน app_id/บัญชีนี้หรือไม่ — ใช้ตอนเจอ error "Symbol ... is invalid"

รัน:
    python -m backend.check_symbols
"""
from __future__ import annotations

import json
import sys

import websocket

from backend.deriv_feed import DERIV_WS_URL, DEFAULT_SYMBOL

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass


def fetch_active_symbols() -> list[dict]:
    ws = websocket.create_connection(DERIV_WS_URL, timeout=15)
    ws.send(json.dumps({"active_symbols": "brief", "product_type": "basic"}))
    raw = ws.recv()
    ws.close()
    data = json.loads(raw)
    if data.get("error"):
        raise RuntimeError(f"Deriv error: {data['error']}")
    return data.get("active_symbols", [])


def main():
    print(f"[check_symbols] กำลังดึง active_symbols จาก {DERIV_WS_URL} ...")
    symbols = fetch_active_symbols()
    print(f"[check_symbols] พบทั้งหมด {len(symbols)} สัญลักษณ์\n")

    exact = [s for s in symbols if s.get("symbol") == DEFAULT_SYMBOL]
    if exact:
        s = exact[0]
        print(f"✅ '{DEFAULT_SYMBOL}' มีอยู่จริงบนบัญชีนี้: "
              f"{s.get('display_name')} (market={s.get('market')}, "
              f"submarket={s.get('submarket')})")
    else:
        print(f"❌ ไม่พบ '{DEFAULT_SYMBOL}' ในรายการ active_symbols ของบัญชีนี้")

    gold_like = [
        s for s in symbols
        if "xau" in s.get("symbol", "").lower() or "gold" in s.get("display_name", "").lower()
    ]
    print("\nสัญลักษณ์ที่เกี่ยวกับ Gold/XAU ที่ใช้งานได้จริงบนบัญชีนี้:")
    if not gold_like:
        print("  (ไม่พบเลย — บัญชี/ภูมิภาคนี้อาจไม่มีสิทธิ์เทรด Gold ผ่าน API นี้)")
    for s in gold_like:
        print(f"  - {s.get('symbol')}  |  {s.get('display_name')}  "
              f"(market={s.get('market')}/{s.get('submarket')})")


if __name__ == "__main__":
    main()
