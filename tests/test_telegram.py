"""Characterization tests — backend/telegram.py

ล็อกพฤติกรรม DEV MODE: ถ้าไม่มี TOKEN/CHAT_ID → print ขึ้น console + คืน False
(บังคับ env ว่างทุกเคส — เทสต์ต้องไม่ยิงข้อความจริงเข้า Telegram เด็ดขาด)
"""
import pytest

from backend import telegram
from backend.telegram import _get_config, send_telegram, send_telegram_document


@pytest.fixture(autouse=True)
def no_telegram_env(monkeypatch):
    """บังคับให้ env ว่างเสมอ — load_dotenv(override=False) จะไม่ทับค่าที่ตั้งไว้"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")


def test_get_config_empty(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    token, chat_id = _get_config()
    assert not token
    assert not chat_id


def test_get_config_reads_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    token, chat_id = _get_config()
    assert token == "dummy-token"
    assert chat_id == "12345"


def test_send_telegram_dev_mode_returns_false(capsys):
    ok = send_telegram("ข้อความทดสอบ")
    assert ok is False
    out = capsys.readouterr().out
    assert "DEV MODE" in out
    assert "ข้อความทดสอบ" in out


def test_send_telegram_document_dev_mode_returns_false(capsys, tmp_path):
    f = tmp_path / "dummy.txt"
    f.write_text("hello", encoding="utf-8")
    ok = send_telegram_document(f, caption="caption ทดสอบ")
    assert ok is False
    out = capsys.readouterr().out
    assert "DEV MODE" in out


def test_send_telegram_with_token_but_bad_chat_calls_api(monkeypatch, capsys):
    """มี token (dummy) + chat_id ผิด → ยิงจริงไปที่ api.telegram.org จะได้ 400/401
    → พฤติกรรมเดิม: คืน False และ "ไม่ retry" เพราะ status อยู่ใน (400,401,403,404)

    หมายเหตุ: ใช้ token ปลอม (401) — ไม่ส่งข้อความถึงใครได้จริง
    """
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:invalid-token-for-test")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999999999")
    ok = send_telegram("ห้ามมีคนเห็นข้อความนี้", retries=1)
    assert ok is False
    out = capsys.readouterr().out
    assert "ไม่ retry" in out