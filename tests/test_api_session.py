"""Characterization tests — backend/api.py เฉพาะ session token (HMAC cookie)

ล็อกพฤติกรรมล็อกอินแบบ session: สร้าง token → verify ผ่าน, แก้ 1 ตัวอักษร → ไม่ผ่าน
(import backend.api = สร้าง FastAPI app แบบไม่ start server — ไม่ spawn engine)
"""
import pytest

from backend.api import DASHBOARD_USER, create_session_token, verify_session_token


def test_token_roundtrip_for_configured_user():
    """token ของ user ที่ระบบกำหนด (DASHBOARD_USER ใน .env) → verify ผ่าน"""
    token = create_session_token(DASHBOARD_USER)
    assert verify_session_token(token) is True


def test_token_for_other_user_rejected():
    """พฤติกรรมเดิม: token ลงชื่อ user อื่น → ปฏิเสธแม้ signature ถูกต้อง"""
    token = create_session_token("tester")
    assert verify_session_token(token) is False


def test_token_tampered_signature_fails():
    token = create_session_token("tester")
    b64, sig = token.split(".", 1)
    bad_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert verify_session_token(f"{b64}.{bad_sig}") is False


def test_token_tampered_payload_fails():
    token = create_session_token(DASHBOARD_USER)
    b64, sig = token.split(".", 1)
    # เปลี่ยน payload ให้เป็น user อื่น (ยังเป็น base64 ที่ถอดได้)
    import base64
    import json
    payload = json.loads(base64.urlsafe_b64decode(b64 + "=="))
    payload["u"] = "attacker"
    new_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode("utf-8")).decode("ascii")
    assert verify_session_token(f"{new_b64}.{sig}") is False


def test_token_garbage_fails():
    assert verify_session_token("") is False
    assert verify_session_token("not-a-token") is False
    assert verify_session_token("x.y") is False


def test_token_expires_in_future():
    import base64
    import json
    import time
    token = create_session_token(DASHBOARD_USER)
    b64, _ = token.split(".", 1)
    payload = json.loads(base64.urlsafe_b64decode(b64 + "=="))
    # exp ต้องอยู่ในอนาคต (session มีอายุวันทำการ)
    assert payload["exp"] > time.time()