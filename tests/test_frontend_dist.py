"""frontend/dist — build output ของ dashboard ต้องพร้อมเสมอ (VPS ไม่มี Node จึง commit dist ไว้)"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend import api


def test_dist_index_exists_and_assets_present():
    dist = Path(api.FRONTEND_DIR) / "dist"
    html = (dist / "index.html").read_text(encoding="utf-8")
    assets = re.findall(r'(?:src|href)="(/static/dist/assets/[^"]+)"', html)
    assert assets, "dist/index.html ไม่อ้าง asset ใต้ /static/dist/assets — build ผิดไปจาก base ที่กำหนด"
    for a in assets:
        assert (dist / a.removeprefix("/static/dist/")).exists(), f"asset หาย: {a}"


def test_root_endpoint_serves_built_dashboard(monkeypatch):
    # ไม่ใช้ `with TestClient(...)` → ไม่รัน startup (กัน migration แตะ DB ตอนรันเทสต์)
    # ปิด auth เฉพาะเทสต์นี้ (ตามพฤติกรรมจริงของ require_auth เมื่อไม่ได้ตั้ง DASHBOARD_USER/PASS)
    monkeypatch.setattr(api, "DASHBOARD_USER", None)
    monkeypatch.setattr(api, "DASHBOARD_PASS", None)
    client = TestClient(api.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "/static/dist/assets/" in r.text
