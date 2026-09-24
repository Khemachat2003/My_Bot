"""
test_ws_handshake.py — เช็คว่า WebSocket upgrade (ไม่ใช่แค่ TLS) ผ่านหรือไม่
รัน: python test_ws_handshake.py
"""
import json
import websocket

websocket.enableTrace(True)  # โชว์ raw handshake/frame ทุกอย่างที่ส่ง-รับ

URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

print("=== พยายามเปิด WebSocket connection (แบบ synchronous, timeout 10s) ===\n")
try:
    ws = websocket.create_connection(URL, timeout=10)
    print("\n>>> WebSocket handshake สำเร็จ! ส่ง request ขอแท่งเทียน...")

    req = {
        "ticks_history": "frxXAUUSD",
        "adjust_start_time": 1,
        "count": 5,
        "end": "latest",
        "start": 1,
        "style": "candles",
        "granularity": 60,
    }
    ws.send(json.dumps(req))

    response = ws.recv()
    print("\n>>> ได้ response กลับมา:")
    print(response[:500])

    ws.close()

except Exception as e:
    print(f"\n>>> FAIL: {type(e).__name__}: {e}")
    print("\nถ้าเห็น error ตรงนี้ (ไม่ใช่แค่ trace log ด้านบน) แปลว่า WebSocket upgrade ถูกบล็อก")
