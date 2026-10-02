# code_map.md — อยากแก้อะไร → ไปที่ไฟล์ไหน (คน + AI agent ใช้เหมือนกัน)

> อ่าน AGENTS.md (root) ก่อน — ไฟล์นี้เป็นแผนที่จุดแก้ ไม่ต้องกวาดอ่านทั้งโปรเจกต์

## Frontend (`frontend/src/**` — แก้แล้วต้อง `npm run build` + commit `dist/`)

| อยากแก้ | ไปที่ไฟล์ | ข้อมูลจาก (API) |
|---|---|---|
| สี/ธีม/ฟอนต์ | `styles/tokens.css` | - |
| ลำดับ CSS (cascade) | `styles/index.css` | - (ห้ามสลับลำดับเดิม) |
| เลย์เอาต์ responsive | `styles/responsive.css` | - |
| แถบบน (brand/ราคา/session) | `features/status-bar/topbar.html` + `headerStatus.js` | `/api/ml/latest` |
| แถบสถานะล่าง | `features/status-bar/statusbar.html` | - |
| สลับแท็บ sidebar | `app/tabs.js` + `app/sidebar.html` | - |
| กราฟหลัก (สร้าง/pane) | `features/chart/lwChartInit.js` | - |
| วาดแท่งเทียน/indicator | `features/chart/drawLwChart.js` + `seriesTransforms.js` | `/api/candles` |
| legend เหนือกราฟ | `features/chart/chartLegend.js` | - |
| toolbar/เส้น S/R/เต็มจอ | `features/chart/chartControls.js` | - |
| ดึงแท่งเทียน + markers | `features/chart/refreshPrice.js` | `/api/candles`, `/api/signals/markers` |
| Watchlist | `features/watchlist/watchlist.js`, `symbols.js` | `/api/watchlist`, `/api/symbols` |
| Probability gauge | `features/gauges/gauges.js` | `/api/ml/latest` |
| สถิติหน้าภาพรวม | `features/overview/refreshOverview.js` | `/api/ml/stats`, `/api/stats`, `/api/journal/stats` |
| กราฟ equity ภาพรวม | `features/overview/drawEquity.js` + `shared/lib/equityData.js` | `/api/journal/stats`, `/api/cfd/paper` |
| แท็บ ML สัญญาณ | `features/ml-signals/refreshMlTab.js`, `feedRow.js` | `/api/ml/*` |
| แท็บ Rule-Based | `features/setup-signals/refreshSetupTab.js` | `/api/stats`, `/api/signals` |
| การ์ด 11-Checklist | `features/setup-signals/setupCards.js` | `/api/setup/latest-all` |
| research แตะ EMA200 | `features/setup-signals/tickTouchResearch.js` | `/api/ticktouch/stats` |
| Journal P&L | `features/journal/*` | `/api/journal/*`, `/api/models` |
| CFD backtest/paper | `features/cfd/backtest.js`, `paperTrading.js` | `/api/cfd/*` |
| แจ้งเตือนสัญญาณใหม่ | `features/notifications/newSignalAlert.js` | `/api/signals?limit=5` |
| toast | `shared/ui/toast.js` | - |
| เรียก API (ที่เดียวเท่านั้น) | `shared/api/client.js` | ทุก endpoint |
| format เวลา/เงิน/signal | `shared/lib/formatTime.js`, `formatSignal.js` | - |
| พับ/ขยาย section | `shared/ui/collapsibles.js` | - |

## Backend (`backend/**`)

| อยากแก้ | ไปที่ไฟล์ | เกี่ยวข้อง (เทสต์/ห้าม) |
|---|---|---|
| สูตร 11-Checklist / สัญญาณ | `setup_scorer.py`, `setup_feed.py` | **⛔ logic เทรด — ถามก่อน** · `tests/test_setup_scorer.py` |
| การยิง/กรองสัญญาณ ML | `notifier.py`, `ml_forecaster/` | **⛔ logic เทรด — ถามก่อน** |
| endpoint `/api/*` | `api.py` (Phase B จะแยกเป็น routes) | `docs/api_contract.md` · ห้ามเปลี่ยน response เดิม |
| auth dashboard | `api.py` (require_auth/session) | **⛔ ห้ามแตะโดยไม่ถาม** · `tests/test_api_session.py` |
| ตาราง/SQL | `db.py` (ตารางกลาง), `setup_db.py` (Setup) | `tests/test_db_*.py` |
| ราคา/Deriv WS | `data_feed/deriv_feed.py` | `tests/test_deriv_feed.py` |
| เวลาตลาด/fallback symbol | `market_hours.py` | `tests/test_market_hours.py` |
| Telegram | `telegram.py` | `tests/test_telegram.py` |
| อินดิเคเตอร์ (สูตรเทรด) | `indicators.py` | **⛔ logic เทรด — ถามก่อน** · `tests/test_indicators.py` |
| backup / macro | `backup.py`, `macro_feed.py` | - |

## อื่นๆ

| อยากแก้ | ไปที่ไฟล์ |
|---|---|
| ส่งออเดอร์ MT5 | `executor/mt5_executor.py` — **⛔ ถามก่อนทุกครั้ง** |
| deploy ขึ้น VPS | `.github/workflows/deploy.yml` + `docker-compose.yml` + `deploy/` |
| สั่งรันทุกระบบ | `run_live.py` |
| เอกสาร/แผน | `docs/` |
