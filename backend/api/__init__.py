"""
api package — dashboard FastAPI (เดิม backend/api.py ~926 บรรทัด)

Phase B (move-only): แยกเป็น package แต่ **ห้ามเปลี่ยนพฤติกรรม** — paths/
responses/auth เหมือนเดิมทั้งหมด ยังรันด้วยคำสั่งเดิม `uvicorn backend.api:app`

โครงของ package:
- ไฟล์นี้ (module `backend.api`) เก็บ: app + ระบบ auth ทั้งหมด (require_auth /
  session token / DASHBOARD_USER/PASS) + /login /logout /api/health
  เหตุผลที่ auth ต้องอยู่ที่นี่เท่านั้น: tests patch `api.DASHBOARD_USER`
  แล้ว require_auth อ่าน global ของ module นี้ตอน call-time
  (ดู tests/test_frontend_dist.py, tests/test_api_endpoints.py)
- backend/api/schemas.py   ← pydantic Body models (schema กลาง)
- backend/api/routes/      ← APIRouter ตามกลุ่ม endpoint
    market.py         /api/symbol /api/symbols /api/candles /api/watchlist /api/prices
    signals_setup.py  /api/signals* /api/ticktouch/stats /api/stats* /api/setup/*
    ml.py             /api/ml/*
    journal.py        /api/journal/* /api/models
    cfd.py            /api/cfd/*
    web.py            GET / (เสิร์ฟหน้า dist)

ตั้ง basic auth (แนะนำก่อน deploy ขึ้น server จริงที่เข้าได้จากมือถือ/อินเทอร์เน็ต):
    ใส่ใน .env → DASHBOARD_USER=xxx และ DASHBOARD_PASS=xxx
    ถ้าไม่ตั้ง จะไม่มี auth (สะดวกตอน dev บน localhost)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

from backend import db, setup_db
from backend.api.schemas import LoginBody

ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # backend/api/__init__.py → root
FRONTEND_DIR = ROOT_DIR / "frontend"

# ── .env + credentials (auth ทั้งหมดอยู่ใน module `backend.api` เท่านั้น) ─────
load_dotenv(ROOT_DIR / ".env")
DASHBOARD_USER = os.getenv("DASHBOARD_USER")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS")

security = HTTPBasic(auto_error=False)

# ── กันรหัสผ่านเริ่มต้นจาก .env.example (คนแปลกหน้า brute-force
# admin/change-me-please บน VPS ที่เปิด port สาธารณะ)
_DEFAULT_USER = "admin"
_DEFAULT_PASS = "change-me-please"


def _default_creds_used() -> bool:
    """True ถ้ายังใช้ user/pass ค่าเริ่มต้นของ .env.example"""
    return DASHBOARD_USER == _DEFAULT_USER and DASHBOARD_PASS == _DEFAULT_PASS


def _is_localhost(request: Request) -> bool:
    try:
        host = request.client.host if request.client else ""
    except Exception:
        host = ""
    return host in ("127.0.0.1", "::1", "localhost", "testclient")


_SESSION_COOKIE = "xauusd_session"
_SESSION_DAYS = 7


# ── Session cookie (HMAC-signed, ไม่มี dependency เพิ่ม) ─────────────────────
def _cookie_secret() -> str:
    """ใช้ DASHBOARD_PASS เป็น seed — เปลี่ยนรหัสผ่าน = เซสชันเก่าใช้ไม่ได้"""
    return (DASHBOARD_PASS or "xauusd-bot-dev") + "::xauusd::bot"


def _sign(raw: str) -> str:
    return hmac.new(
        _cookie_secret().encode("utf-8"), raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def create_session_token(username: str) -> str:
    payload = json.dumps({"u": username, "exp": int(time.time()) + _SESSION_DAYS * 86400})
    b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    return f"{b64}.{_sign(b64)}"


def verify_session_token(token: str) -> bool:
    try:
        b64, sig = token.split(".", 1)
        if not hmac.compare_digest(_sign(b64), sig):
            return False
        payload = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")).decode("utf-8"))
        if payload.get("u") != DASHBOARD_USER:
            return False
        return int(payload.get("exp", 0)) > time.time()
    except Exception:
        return False


def require_auth(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    """ถ้าไม่ได้ตั้ง DASHBOARD_USER/PASS ใน .env จะปล่อยผ่านหมด (สำหรับ localhost dev).

    รองรับ 2 แบบ: HTTP Basic (API/curl เดิม) หรือ session cookie จากหน้า /login
    — หน้าเว็บ / หรือ /static ไม่มีสิทธิ์ → เปลี่ยนไปหน้า login (ทำงานในทุกเบราว์เซอร์
    รวมถึง VS Code ที่ basic-auth dialog ไม่โชว์), API → 401 JSON ตามปกติ
    """
    if not DASHBOARD_USER or not DASHBOARD_PASS:
        return True
    if credentials is not None:
        ok_user = secrets.compare_digest(credentials.username, DASHBOARD_USER)
        ok_pass = secrets.compare_digest(credentials.password, DASHBOARD_PASS)
        if ok_user and ok_pass:
            if _default_creds_used() and not _is_localhost(request):
                print(
                    "[Security] ❌ ปฏิเสธ login ด้วยรหัสผ่านเริ่มต้นจาก IP ภายนอก — "
                    "ตั้ง DASHBOARD_USER/DASHBOARD_PASS ใน .env ก่อน (ดู .env.example)"
                )
                raise HTTPException(
                    status_code=403,
                    detail="รหัสผ่านเริ่มต้นใช้ได้เฉพาะ localhost — ตั้ง DASHBOARD_USER/DASHBOARD_PASS ใน .env ก่อน",
                )
            return True
    token = request.cookies.get(_SESSION_COOKIE)
    if token and verify_session_token(token):
        return True
    if request.url.path.startswith("/api/"):
        raise HTTPException(
            status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"}
        )
    raise HTTPException(status_code=307, headers={"Location": "/login"})


# ── /docs + /openapi.json ปิดเป็นค่า default (กันเปิดเผยโครงสร้าง API ทั้งหมด
#    บน VPS ที่เข้าถึงได้จากอินเทอร์เน็ต) — เปิดเฉพาะตอน dev: DOCS_ENABLED=1 ──
_DOCS_KW = (
    {}
    if os.getenv("DOCS_ENABLED") == "1"
    else {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
)
app = FastAPI(title="XAUUSD Bot Dashboard", **_DOCS_KW)


@app.on_event("startup")
def _startup():
    db.init_db()
    setup_db.init_setup_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "xauusd-bot"}


# ── หน้า login (session cookie — ใช้ได้กับทุกเบราว์เซอร์ รวมถึง VS Code) ────
# เก็บไว้ในไฟล์นี้พร้อมระบบ auth เพราะ login_page/login อ่าน DASHBOARD_USER/PASS
# ณ runtime (ต้องตอบสนองต่อการ patch ค่าใน tests — ห้าม bind เป็นค่าตายตอน import)
_LOGIN_MSG = ""
# ไม่เฉลย user/pass เริ่มต้นบนหน้า login (กันคนแปลกหน้าลองรหัสผ่านจากที่เห็นบนหน้าเว็บ)
_HINT = "<div class='hint'>ชื่อผู้ใช้/รหัสผ่านตั้งได้ในไฟล์ .env → DASHBOARD_USER / DASHBOARD_PASS</div>"

LOGIN_HTML = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>XAUUSD Bot — เข้าสู่ระบบ</title>
<style>
  body{{font-family:Segoe UI,Arial,sans-serif;background:#0f1420;color:#e8e8e8;
       display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
  .card{{background:#1a2233;padding:36px 40px;border-radius:12px;
        box-shadow:0 8px 30px rgba(0,0,0,.4);width:320px}}
  h1{{font-size:19px;margin:0 0 4px}}
  .sub{{color:#9aa4b8;font-size:13px;margin:0 0 22px}}
  label{{display:block;font-size:12px;color:#9aa4b8;margin:12px 0 4px}}
  input{{width:100%;box-sizing:border-box;padding:10px;border-radius:6px;
        border:1px solid #2c3b4e;background:#0f1420;color:#e8e8e8;font-size:14px}}
  input:focus{{outline:none;border-color:#4c8dff}}
  button{{width:100%;margin-top:18px;padding:11px;border:none;border-radius:6px;
         background:#2f6feb;color:#fff;font-size:15px;cursor:pointer}}
  button:hover{{background:#3d7cf5}}
  .err{{color:#ff6b6b;font-size:13px;margin:0 0 8px;min-height:18px}}
  .hint{{color:#6b7688;font-size:12px;margin-top:16px;line-height:1.6}}
  code{{background:#0f1420;padding:1px 5px;border-radius:4px}}
</style>
</head>
<body>
<div class="card">
  <h1>🔐 XAUUSD Bot Dashboard</h1>
  <p class="sub">กรอกชื่อผู้ใช้และรหัสผ่านเพื่อเข้าดู</p>
  <div class="err" id="err"></div>
  <form id="loginForm">
    <label>Username</label>
    <input name="username" autocomplete="username" required>
    <label>Password</label>
    <input type="password" name="password" autocomplete="current-password" required>
    <button type="submit">เข้าสู่ระบบ</button>
  </form>
  {_HINT}
</div>
<script>
  document.getElementById('loginForm').addEventListener('submit', async (e) => {{
    e.preventDefault();
    const f = e.target;
    const res = await fetch('/login', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        username: f.username.value,
        password: f.password.value
      }})
    }});
    if (res.redirected) {{ location.href = res.url; }}
    else {{
      const data = await res.json().catch(() => ({{}}));
      document.getElementById('err').textContent =
        data.detail || 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง';
    }}
  }});
</script>
</body>
</html>
"""


@app.get("/login", response_class=HTMLResponse)
def login_page():
    if not DASHBOARD_USER or not DASHBOARD_PASS:
        return RedirectResponse("/", status_code=303)
    return LOGIN_HTML


@app.post("/login")
def login(body: LoginBody, request: Request):
    if not DASHBOARD_USER or not DASHBOARD_PASS:
        return RedirectResponse("/", status_code=303)
    ok_user = secrets.compare_digest(body.username, DASHBOARD_USER)
    ok_pass = secrets.compare_digest(body.password, DASHBOARD_PASS)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    # กัน brute-force จากอินเทอร์เน็ต: ถ้ายังใช้ user/pass เริ่มต้น → อนุญาตเฉพาะ localhost
    if _default_creds_used() and not _is_localhost(request):
        print(
            f"[Security] ❌ ปฏิเสธ login ด้วยรหัสผ่านเริ่มต้นจาก IP ภายนอก "
            f"({request.client.host if request.client else '?'}) — ตั้ง DASHBOARD_USER/DASHBOARD_PASS ใน .env ก่อน"
        )
        raise HTTPException(
            status_code=403,
            detail="รหัสผ่านเริ่มต้นใช้ได้เฉพาะ localhost — ตั้ง DASHBOARD_USER/DASHBOARD_PASS ใน .env ก่อน",
        )
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        _SESSION_COOKIE,
        create_session_token(body.username),
        max_age=_SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
    )
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(_SESSION_COOKIE)
    return resp


# ── routers ตามกลุ่ม endpoint (import "หลัง" require_auth — routes modules
#    อ้าง require_auth ผ่าน `from backend.api import require_auth` ตอน import
#    ซึ่งเกิดระหว่าง initialization ของ package นี้ จึงต้องอยู่ท้ายไฟล์)
from backend.api.routes import cfd, journal, market, ml, signals_setup, web  # noqa: E402

app.include_router(market.router)
app.include_router(signals_setup.router)
app.include_router(ml.router)
app.include_router(journal.router)
app.include_router(cfd.router)
app.include_router(web.router)

# ── serve ไฟล์ static ของ frontend (vendor + dist/assets) เหมือนเดิม ─────────
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
