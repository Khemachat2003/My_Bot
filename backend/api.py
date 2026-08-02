"""
api.py — Phase 3: เว็บ dashboard สำหรับดู log/ผล/ราคา ของสัญญาณสด

รันแยก process จาก notifier.py (notifier ยิงสัญญาณ+เขียน DB, api แค่ "อ่าน"
DB มาโชว์) ทั้งคู่เขียน/อ่าน sqlite ไฟล์เดียวกันที่ data/bot.db พร้อมกันได้
เพราะเปิด WAL mode ไว้ใน db.py

รัน (localhost):
    pip install fastapi "uvicorn[standard]"
    uvicorn backend.api:app --reload --port 8000
แล้วเปิดเบราว์เซอร์ที่ http://localhost:8000

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
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import db
from backend import setup_db

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

load_dotenv(ROOT_DIR / ".env")
DASHBOARD_USER = os.getenv("DASHBOARD_USER")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS")

security = HTTPBasic(auto_error=False)

_SESSION_COOKIE = "xauusd_session"
_SESSION_DAYS = 7


# ── Session cookie (HMAC-signed, ไม่มี dependency เพิ่ม) ─────────────────────
def _cookie_secret() -> str:
    """ใช้ DASHBOARD_PASS เป็น seed — เปลี่ยนรหัสผ่าน = เซสชันเก่าใช้ไม่ได้"""
    return (DASHBOARD_PASS or "xauusd-bot-dev") + "::xauusd::bot"


def _sign(raw: str) -> str:
    return hmac.new(_cookie_secret().encode("utf-8"), raw.encode("utf-8"),
                    hashlib.sha256).hexdigest()


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
            return True
    token = request.cookies.get(_SESSION_COOKIE)
    if token and verify_session_token(token):
        return True
    if request.url.path.startswith("/api/"):
        raise HTTPException(status_code=401, detail="Unauthorized",
                             headers={"WWW-Authenticate": "Basic"})
    raise HTTPException(status_code=307, headers={"Location": "/login"})


app = FastAPI(title="XAUUSD Bot Dashboard")


@app.on_event("startup")
def _startup():
    db.init_db()
    setup_db.init_setup_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "xauusd-bot"}


# ── หน้า login (session cookie — ใช้ได้กับทุกเบราว์เซอร์ รวมถึง VS Code) ────
_LOGIN_MSG = ""
_HINT = ("<div class='hint'>ค่าเริ่มต้น: <code>admin</code> / <code>change-me-please</code>"
         "<br>แก้ได้ในไฟล์ .env → DASHBOARD_USER / DASHBOARD_PASS</div>" if DASHBOARD_PASS == "change-me-please"
         else "<div class='hint'>ชื่อผู้ใช้/รหัสผ่านอยู่ในไฟล์ .env → DASHBOARD_USER / DASHBOARD_PASS</div>")

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


class LoginBody(BaseModel):
    username: str
    password: str


@app.get("/login", response_class=HTMLResponse)
def login_page():
    if not DASHBOARD_USER or not DASHBOARD_PASS:
        return RedirectResponse("/", status_code=303)
    return LOGIN_HTML


@app.post("/login")
def login(body: LoginBody):
    if not DASHBOARD_USER or not DASHBOARD_PASS:
        return RedirectResponse("/", status_code=303)
    ok_user = secrets.compare_digest(body.username, DASHBOARD_USER)
    ok_pass = secrets.compare_digest(body.password, DASHBOARD_PASS)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(_SESSION_COOKIE, create_session_token(body.username),
                    max_age=_SESSION_DAYS * 86400, httponly=True, samesite="lax")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(_SESSION_COOKIE)
    return resp


@app.get("/api/prices")
def get_prices(limit: int = Query(500, ge=1, le=5000), _auth=Depends(require_auth)):
    """ราคา/กราฟ ใช้ร่วมกันทั้ง 2 ระบบ"""
    return db.fetch_recent_prices(limit=limit)


# ── 🔵 RULE-BASED SETUP ENGINE (System 1) ───────────────────────────────
@app.get("/api/signals")
def get_signals(limit: int = Query(100, ge=1, le=1000), _auth=Depends(require_auth)):
    return db.fetch_recent_setup_signals(limit=limit)


@app.get("/api/stats")
def get_stats(payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)):
    return db.compute_setup_stats(payout=payout)


@app.get("/api/stats/by_timeframe")
def get_stats_by_timeframe(payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)):
    """Winrate แยกตาม timeframe (M1/M5) แบบ real-time — {"M1": {...}, "M5": {...}}"""
    return db.compute_setup_stats_by_timeframe(payout=payout)


@app.get("/api/setup/latest")
def get_setup_latest(_auth=Depends(require_auth)):
    """ผลล่าสุดของ setup_scorer checklist ต่อ timeframe → {"1m": {...}, "5m": {...}}"""
    return setup_db.fetch_latest_setup_scores()


@app.get("/api/setup/history")
def get_setup_history(
    timeframe: str = Query("M1", pattern="^(M1|M5)$"),
    limit: int = Query(50, ge=1, le=500),
    _auth=Depends(require_auth),
):
    return setup_db.fetch_recent_setup_scores(timeframe, limit=limit)


# ── 🟢 ML MODEL ENGINE (System 2) ────────────────────────────────────────
@app.get("/api/ml/signals")
def get_ml_signals(limit: int = Query(100, ge=1, le=1000), _auth=Depends(require_auth)):
    return db.fetch_recent_ml_signals(limit=limit)


@app.get("/api/ml/stats")
def get_ml_stats(payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)):
    return db.compute_ml_stats(payout=payout)


@app.get("/api/ml/stats/by_timeframe")
def get_ml_stats_by_timeframe(payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)):
    return db.compute_ml_stats_by_timeframe(payout=payout)


@app.get("/api/ml/latest")
def get_ml_latest(_auth=Depends(require_auth)):
    """ค่า prob_up/prob_down ล่าสุดต่อ timeframe → Real-time Probability Gauge"""
    return db.fetch_ml_latest()


# ── 📓 Trade Journal & Model Registry ─────────────────────────────────────────
@app.get("/api/journal")
def get_journal(limit: int = Query(100, ge=1, le=1000), _auth=Depends(require_auth)):
    return db.fetch_recent_trades(limit=limit)


@app.get("/api/journal/stats")
def get_journal_stats(payout: float = Query(0.82, ge=0.0, le=5.0), _auth=Depends(require_auth)):
    """P&L รวม + equity curve + daily breakdown จาก trade_journal"""
    return db.compute_journal_stats(payout=payout)


@app.get("/api/models")
def get_models(_auth=Depends(require_auth)):
    """model registry — ดู version โมเดลที่เคยเทรนทั้งหมด"""
    return db.fetch_model_registry(limit=50)


# ── serve หน้าเว็บ dashboard ────────────────────────────────────────────────
@app.get("/")
def index(_auth=Depends(require_auth)):
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
