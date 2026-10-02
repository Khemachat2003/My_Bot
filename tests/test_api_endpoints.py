"""Characterization tests — endpoint ของ backend.api (ก่อน/หลังแยกเป็น backend/api/)

ล็อก shape ของ /api/* ตาม docs/api_contract.md:
- TestClient ไม่ใช้ `with` → ไม่รัน startup event (กัน migration แตะ DB จริง)
- auth ปิด/เปิดผ่าน fixture (patch DASHBOARD_USER/PASS — ไม่แตะระบบ auth จริง)
- DB ชี้ไฟล์ชั่วคราวทั้ง backend.db และ setup_db
- ปิด network จริงด้วย patch fetch_candles_history
"""

from __future__ import annotations

import pytest

import backend.db as db


def _seed_setup_signal(**over) -> int:
    kwargs = dict(
        signal_time="2026-01-01T00:00:00+00:00",
        entry_price=2000.0,
        direction="CALL",
        confidence=0.6,
        horizon_min=15,
        target_time="2026-01-01T00:15:00+00:00",
    )
    kwargs.update(over)
    return db.insert_setup_signal(**kwargs)


def _seed_ml_signal(**over) -> int:
    kwargs = dict(
        signal_time="2026-01-01T00:00:00+00:00",
        entry_price=2000.0,
        direction="CALL",
        confidence=0.6,
        horizon_min=15,
        target_time="2026-01-01T00:15:00+00:00",
    )
    kwargs.update(over)
    return db.insert_ml_signal(**kwargs)


def test_health_exact_shape(api_client):
    r = api_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "xauusd-bot"}


def test_symbol_keys(api_client):
    r = api_client.get("/api/symbol")
    assert r.status_code == 200
    assert set(r.json()) == {"symbol", "label"}


def test_symbols_list(api_client):
    r = api_client.get("/api/symbols")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_candles_empty_without_data(api_client):
    # deriv ถูก patch → None + DB ว่าง → fallback คืน [] (ไม่ยิง network)
    r = api_client.get("/api/candles", params={"tf": "1m", "count": 5})
    assert r.status_code == 200
    assert r.json() == []


def test_prices_shape_after_seed(api_client):
    db.insert_price("2026-01-01T00:00:00+00:00", 2000.0, 2001.0, 1999.0, 2000.5)
    db.insert_price("2026-01-01T00:01:00+00:00", 2000.5, 2002.0, 2000.0, 2001.0)
    r = api_client.get("/api/prices", params={"limit": 5, "symbol": "frxXAUUSD"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert set(rows[0]) == {"ts", "symbol", "open", "high", "low", "close"}
    assert [x["ts"] for x in rows] == [  # เก่า → ใหม่
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:01:00+00:00",
    ]


def test_signals_shape_after_seed(api_client):
    sid = _seed_setup_signal(score=11, total=15)
    r = api_client.get("/api/signals", params={"limit": 10, "symbol": "frxXAUUSD"})
    assert r.status_code == 200
    rows = r.json()
    assert [x["id"] for x in rows] == [sid]
    for key in (
        "signal_time",
        "entry_price",
        "direction",
        "confidence",
        "horizon_min",
        "target_time",
        "timeframe",
        "result",
    ):
        assert key in rows[0]


def test_markers_shape_with_cfd(api_client):
    sid = _seed_setup_signal()
    db.insert_cfd_paper_trade(
        signal_id=sid,
        signal_type="SETUP",
        symbol="frxXAUUSD",
        direction="CALL",
        entry_price=2000.0,
        entry_time="2026-01-01T00:00:00+00:00",
    )
    r = api_client.get("/api/signals/markers", params={"symbol": "frxXAUUSD", "limit": 50})
    assert r.status_code == 200
    markers = r.json()
    assert len(markers) == 1
    m = markers[0]
    for key in ("type", "ts", "price", "direction", "result", "id"):
        assert key in m
    assert m["type"] == "SETUP" and m["id"] == sid
    for key in ("effective_entry", "sl", "tp1", "tp2", "pnl", "cfd_result"):
        assert key in m["cfd"]


def test_ticktouch_stats_keys(api_client):
    r = api_client.get("/api/ticktouch/stats")
    assert r.status_code == 200
    for key in ("total", "pending", "resolved", "wins", "wr", "by_case", "by_condition", "recent"):
        assert key in r.json()


def test_stats_exact_keys(api_client):
    r = api_client.get("/api/stats")
    assert r.status_code == 200
    assert set(r.json()) == {
        "n_resolved",
        "wins",
        "losses",
        "draws",
        "n_pending",
        "winrate",
        "ci_low",
        "ci_high",
        "breakeven",
        "margin",
        "payout",
    }


def test_stats_by_timeframe(api_client):
    _seed_setup_signal(timeframe="M1")
    _seed_setup_signal(
        timeframe="M5",
        signal_time="2026-01-01T00:20:00+00:00",
        target_time="2026-01-01T00:35:00+00:00",
    )
    r = api_client.get("/api/stats/by_timeframe")
    assert r.status_code == 200
    assert set(r.json()) == {"M1", "M5"}


def test_setup_endpoints_ok(api_client):
    # ตาราง setup_scores ว่าง → 200 (ล็อกแค่ route + auth ผ่าน)
    assert api_client.get("/api/setup/latest").status_code == 200
    assert api_client.get("/api/setup/latest-all").status_code == 200
    assert (
        api_client.get(
            "/api/setup/history", params={"timeframe": "M1", "symbol": "frxXAUUSD"}
        ).status_code
        == 200
    )


def test_ml_endpoints_after_seed(api_client):
    mid = _seed_ml_signal(prob_up=0.62, prob_down=0.38)
    r = api_client.get("/api/ml/signals")
    assert r.status_code == 200 and r.json()[0]["id"] == mid
    stats = api_client.get("/api/ml/stats").json()
    assert set(stats) == {
        "n_resolved",
        "wins",
        "losses",
        "draws",
        "n_pending",
        "winrate",
        "ci_low",
        "ci_high",
        "breakeven",
        "margin",
        "payout",
    }
    assert set(api_client.get("/api/ml/stats/by_timeframe").json()) == {"M1"}
    assert api_client.get("/api/ml/latest").json() == {}  # ยังไม่มี upsert


def test_ml_latest_after_upsert(api_client):
    db.upsert_ml_latest("M1", "2026-01-01T00:00:00+00:00", 0.62, 0.38, "CALL", 0.62, 0.57)
    data = api_client.get("/api/ml/latest").json()
    assert set(data) == {"M1"}
    for key in ("ts", "prob_up", "prob_down", "signal", "confidence", "threshold_used"):
        assert key in data["M1"]


def test_journal_endpoints_after_seed(api_client):
    sid = _seed_setup_signal()
    tid = db.insert_trade(
        signal_id=sid,
        signal_type="SETUP",
        timeframe="M1",
        symbol="frxXAUUSD",
        direction="CALL",
        entry_price=2000.0,
        entry_time="2026-01-01T00:00:00+00:00",
        hold_min=15,
    )
    r = api_client.get("/api/journal")
    assert r.status_code == 200
    rows = r.json()
    assert [x["id"] for x in rows] == [tid]
    for key in (
        "signal_type",
        "timeframe",
        "symbol",
        "direction",
        "entry_price",
        "entry_time",
        "hold_min",
        "result",
    ):
        assert key in rows[0]


def test_journal_stats_keys(api_client):
    r = api_client.get("/api/journal/stats")
    assert r.status_code == 200
    assert set(r.json()) == {
        "n",
        "wins",
        "losses",
        "winrate",
        "ci_low",
        "ci_high",
        "breakeven",
        "total_pnl",
        "equity",
        "daily",
    }


def test_journal_settings_defaults_and_post(api_client):
    r = api_client.get("/api/journal/settings")
    assert r.status_code == 200
    assert r.json() == {"capital": 5000.0, "stake": 100.0, "currency": "THB"}

    r = api_client.post("/api/journal/settings", json={"capital": 10000, "stake": 200})
    assert r.status_code == 200
    assert r.json() == {"capital": 10000.0, "stake": 200.0, "currency": "THB"}

    # validate > 0 (พฤติกรรมเดิม)
    assert (
        api_client.post("/api/journal/settings", json={"capital": 0, "stake": 100}).status_code
        == 400
    )
    assert (
        api_client.post("/api/journal/settings", json={"capital": 5000, "stake": -1}).status_code
        == 400
    )


def test_journal_report_keys(api_client):
    r = api_client.get("/api/journal/report")
    assert r.status_code == 200
    data = r.json()
    for key in ("settings", "summary", "cfd_summary", "daily", "weekly", "monthly", "yearly"):
        assert key in data


def test_journal_export_xlsx(api_client):
    r = api_client.get("/api/journal/export")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 0


def test_models_endpoint(api_client):
    db.register_model(
        "M1",
        "v2_meanrev",
        "2026-01-01T00:00:00+00:00",
        5,
        n_rows=1000,
        auc_val=0.55,
        auc_test=0.54,
        chosen_conf=0.57,
    )
    r = api_client.get("/api/models")
    assert r.status_code == 200
    rows = r.json()
    assert rows[0]["model_key"] == "M1" and rows[0]["version"] == "v2_meanrev"


def test_cfd_paper_keys_with_open_trade(api_client):
    sid = _seed_setup_signal()
    db.insert_cfd_paper_trade(
        signal_id=sid,
        signal_type="SETUP",
        symbol="frxXAUUSD",
        direction="CALL",
        entry_price=2000.0,
        entry_time="2026-01-01T00:00:00+00:00",
    )
    r = api_client.get("/api/cfd/paper")
    assert r.status_code == 200
    data = r.json()
    assert data["open"] == 1 and data["total"] == 0
    for key in (
        "sl",
        "tp1",
        "tp2",
        "wr",
        "total_pnl",
        "by_type",
        "by_direction",
        "trades",
        "open_trades",
    ):
        assert key in data


def test_watchlist_shape_after_seed(api_client):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    db.insert_price((now - timedelta(minutes=1)).isoformat(), 2000.0, 2001.0, 1999.0, 2000.5)
    db.insert_price((now - timedelta(minutes=2)).isoformat(), 2000.5, 2002.0, 2000.0, 2001.0)
    r = api_client.get("/api/watchlist", params={"symbols": "frxXAUUSD"})
    assert r.status_code == 200
    item = r.json()[0]
    assert item["symbol"] == "frxXAUUSD"
    assert item["price"] == 2000.5  # ราคาล่าสุด
    assert item["chgPct"] == pytest.approx((2000.5 - 2001.0) / 2001.0 * 100, abs=1e-9)


# ── auth flow (HTTP Basic + session cookie) — ล็อกพฤติกรรมเดิมของ require_auth ──


def test_api_requires_basic_auth(auth_client):
    r = auth_client.get("/api/stats", follow_redirects=False)
    assert r.status_code == 401


def test_api_basic_auth_correct(auth_client):
    assert auth_client.get("/api/stats", auth=("user", "pass")).status_code == 200


def test_api_basic_auth_wrong_password(auth_client):
    assert auth_client.get("/api/stats", auth=("user", "nope")).status_code == 401


def test_health_public_even_with_auth_enabled(auth_client):
    assert auth_client.get("/api/health").status_code == 200


def test_web_page_redirects_to_login(auth_client):
    r = auth_client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/login"


def test_login_page_returns_html(auth_client):
    r = auth_client.get("/login")
    assert r.status_code == 200
    assert "XAUUSD Bot" in r.text


def test_login_correct_sets_session_cookie(auth_client):
    r = auth_client.post(
        "/login", json={"username": "user", "password": "pass"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert "xauusd_session" in r.cookies
    # session cookie ต้องผ่าน require_auth ได้ (แทน basic auth)
    assert auth_client.get("/api/stats").status_code == 200


def test_login_wrong_password_rejected(auth_client):
    r = auth_client.post("/login", json={"username": "user", "password": "nope"})
    assert r.status_code == 401


def test_logout_redirects_to_login(auth_client):
    auth_client.post("/login", json={"username": "user", "password": "pass"})
    r = auth_client.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
