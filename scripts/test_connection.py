"""
test_connection.py — เช็คว่าเน็ต/ไฟร์วอลล์บล็อกการต่อ Deriv อยู่หรือไม่
รัน: python test_connection.py
"""
import socket
import ssl

HOST = "ws.derivws.com"
PORT = 443

print(f"1) เช็ค DNS resolve {HOST} ...")
try:
    ip = socket.gethostbyname(HOST)
    print(f"   OK → {ip}")
except Exception as e:
    print(f"   FAIL: {e}")
    print("   → DNS หา domain ไม่เจอ อาจถูก DNS-level block โดย ISP")
    raise SystemExit

print(f"2) เช็ค TCP connect ไปที่ {HOST}:{PORT} (timeout 8s) ...")
try:
    sock = socket.create_connection((HOST, PORT), timeout=8)
    print("   OK → เชื่อมต่อ TCP ได้")
    sock.close()
except Exception as e:
    print(f"   FAIL: {e}")
    print("   → ISP/Firewall/Router น่าจะบล็อกพอร์ต 443 ไปยัง host นี้โดยเฉพาะ")
    raise SystemExit

print(f"3) เช็ค TLS handshake (https) ...")
try:
    ctx = ssl.create_default_context()
    with socket.create_connection((HOST, PORT), timeout=8) as sock:
        with ctx.wrap_socket(sock, server_hostname=HOST) as ssock:
            print(f"   OK → TLS handshake สำเร็จ, cert: {ssock.getpeercert()['subject']}")
except Exception as e:
    print(f"   FAIL: {e}")
    print("   → TLS ถูกดัก/บล็อกกลางทาง (Deep Packet Inspection) — มักเป็นการบล็อกระดับ ISP")
    raise SystemExit

print("\nสรุป: เน็ตต่อ Deriv ได้ปกติทุกระดับ ปัญหาน่าจะอยู่ที่ตัว websocket-client "
      "library หรือ event loop ไม่ใช่การบล็อกเครือข่าย — กลับไปดีบัคที่โค้ดต่อ")
