"""capture_fixtures.py — บันทึก response จริงของ /api/* (GET ที่หน้าเว็บเรียก) ลง fixtures/api.json
ใช้เป็นข้อมูลนิ่งสำหรับเทียบ screenshot ก่อน-หลังแยกไฟล์ (ไม่ยิง backend ระหว่างเทสต์)

รัน (จาก root โปรเจกต์):  ./venv/Scripts/python.exe frontend/tests/visual/capture_fixtures.py
- เรียก backend.api ผ่าน FastAPI TestClient ใน process (ไม่เปิด port, ไม่แตะ VPS)
- อ่าน DASHBOARD_USER/PASS จาก .env ใน process เท่านั้น ไม่พิมพ์/ไม่บันทึกลงไฟล์
- fixtures มีข้อมูลเทรดจริง → git-ignored (ดู frontend/.gitignore)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[3]  # frontend/tests/visual → root
sys.path.insert(0, str(ROOT))  # ให้ import backend.* ได้เมื่อรันจาก path ใดก็ได้

from fastapi.testclient import TestClient  # noqa: E402

from backend import api  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures" / "api.json"

URLS = [
    "/api/signals?limit=5",
    "/api/signals?limit=100",
    "/api/ml/stats",
    "/api/ml/stats/by_timeframe",
    "/api/ml/signals?limit=100",
    "/api/ml/signals?limit=8",
    "/api/ml/latest",
    "/api/stats",
    "/api/stats/by_timeframe",
    "/api/ticktouch/stats",
    "/api/setup/latest-all",
    "/api/journal/stats",
    "/api/journal/settings",
    "/api/journal/report",
    "/api/cfd/paper",
    "/api/models",
    "/api/symbol",
    "/api/symbols",
    "/api/signals/markers?symbol=frxXAUUSD&limit=50",
    "/api/candles?tf=1m&count=300&symbol=frxXAUUSD",
    "/api/candles?tf=1m&count=1000&symbol=frxXAUUSD",
]


def key_of(url: str) -> str:
    """คีย์มาตรฐาน: path + query เรียงตามชื่อ (ต้องตรงกับ server.mjs)"""
    u = urlsplit(url)
    q = sorted(parse_qsl(u.query, keep_blank_values=True))
    return u.path + ("?" + "&".join(f"{k}={v}" for k, v in q) if q else "")


def main() -> None:
    user, pw = os.getenv("DASHBOARD_USER"), os.getenv("DASHBOARD_PASS")
    auth = (user, pw) if user and pw else None
    out: dict[str, dict] = {}
    # ไม่ใช้ `with TestClient(...)` → ไม่รัน startup (db.init_db() มี migration ที่ลบข้อมูลค้างใน DB)
    # endpoint ทั้งหมดเป็น GET อ่านอย่างเดียว ไม่ต้องพึ่ง startup
    client = TestClient(api.app)
    if True:

        def grab(url: str):
            r = client.get(url, auth=auth)
            body = (
                r.json()
                if r.headers.get("content-type", "").startswith("application/json")
                else None
            )
            out[key_of(url)] = {"status": r.status_code, "body": body}
            print(f"{r.status_code}  {key_of(url)}")
            return body

        for url in URLS:
            grab(url)
        syms = out.get("/api/symbols", {}).get("body") or []
        if isinstance(syms, list) and syms:
            grab("/api/watchlist?symbols=" + ",".join(s["symbol"] for s in syms))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {len(out)} fixtures → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
