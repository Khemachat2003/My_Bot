"""routes/web — เสิร์ฟหน้า dashboard build (dist) ที่ GET /

(ย้ายจาก backend/api.py แบบ move-only — mount /static ยังอยู่ใน
backend/api/__init__.py เพราะต้องเรียก app.mount โดยตรง)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from backend.api import FRONTEND_DIR, ROOT_DIR, require_auth

router = APIRouter()


@router.get("/")
def index(_auth=Depends(require_auth)):
    # หน้า dashboard build ด้วย Vite → frontend/dist (commit ไว้ใน git เพราะ VPS ไม่มี Node)
    # กันลืม build: ถ้า dist หาย ให้เสิร์ฟไฟล์เดิมจาก _archive แทน (หน้าขาวดีกว่า 500)
    _dist = FRONTEND_DIR / "dist" / "index.html"
    _legacy = ROOT_DIR / "_archive" / "index.legacy.html"
    return FileResponse(_dist if _dist.exists() else _legacy)
