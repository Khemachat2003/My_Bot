// split.js-map.mjs — แผนที่ "บรรทัด <script> เดิม → module ใหม่" (Phase A, move-only)
// เลขบรรทัดอ้างอิง _archive/index.legacy.html (1-based) — ต้องครอบ 1133–3475 ครบ ไม่ซ้ำ
// ARCHIVE = โค้ดตาย (ไม่มีโค้ด live เรียกใช้) → ย้ายไป _archive/ ไม่ลบ
export const ARCHIVE = '__archive__';
const m = (file, ranges, desc) => ({ file, ranges, desc });

export const JS_MODULES = [
  m('app/refreshLoop.js', [[1133, 1134], [3446, 3459]], 'รอบ refresh: refreshAll() เรียกทุกแผงพร้อมกัน'),
  m('app/boot.js', [[3460, 3466]], 'เริ่มระบบ: โหลด symbol → ขอสิทธิ์แจ้งเตือน → refreshAll ทุก REFRESH_MS'),
  m('features/notifications/newSignalAlert.js', [[1135, 1146], [1164, 1183]],
    'แจ้งเตือนสัญญาณ Setup ใหม่ (toast + Web Notification) — /api/signals?limit=5'),
  m('shared/ui/toast.js', [[1147, 1163]], 'toast มุมขวาบน (ใช้ร่วมทุก feature)'),
  m('shared/lib/formatTime.js', [[1184, 1186]], 'format เวลาแบบไทย (fmtTime / fmtHM)'),
  m('shared/api/client.js', [[1187, 1200]], 'API client กลาง — fetchJSON (timeout 15 วิ)'),
  m('shared/lib/formatSignal.js', [[1201, 1204]], 'format ทิศทาง/margin ของสัญญาณ'),
  m(ARCHIVE, [[1205, 1216], [1219, 1222], [1224, 1245], [1309, 1907]],
    'กราฟ canvas รุ่นเก่า + S/R แบบ canvas (ถูกแทนด้วย lightweight-charts แล้ว ไม่มีโค้ดใดเรียก)'),
  m('features/chart/drawLwChart.js', [[1217, 1218], [2087, 2094], [2241, 2352], [2354, 2354], [2389, 2448]],
    'วาดกราฟแท่งเทียน + indicator + markers + trade list'),
  m('shared/lib/indicators.js', [[1223, 1223], [1246, 1308]], 'RSI / ADX / Fractal สำหรับ "วาดบนกราฟ" เท่านั้น'),
  m('features/gauges/gauges.js', [[1908, 1939], [2761, 2769]], 'Probability Gauge M1/M5 — /api/ml/latest'),
  m('app/tabs.js', [[1940, 1950]], 'สลับแท็บจาก sidebar (data-tab → section#tab-*)'),
  m('shared/ui/domText.js', [[1951, 1955]], 'helper เขียนข้อความ/คลาสลง element'),
  m('features/overview/refreshOverview.js', [[1956, 1995]],
    'สถิติแท็บภาพรวม — /api/ml/stats, /api/stats, /api/journal/stats|settings, /api/cfd/paper, /api/models'),
  m('shared/lib/equityData.js', [[1996, 2027]], 'แปลงข้อมูล equity (journal + CFD paper) เป็นจุดกราฟ'),
  m('features/overview/drawEquity.js', [[2028, 2078]], 'กราฟ Equity Curve ในแท็บภาพรวม'),
  m('features/chart/lwChartInit.js', [[2079, 2086], [2095, 2194]],
    'สร้างกราฟหลัก + pane Volume/RSI/ADX + sync pan/zoom + resize'),
  m('features/chart/seriesTransforms.js', [[2195, 2240]], 'แปลงแท่งเทียน + EMA/SMA/BB สำหรับวาด'),
  m('features/chart/chartLegend.js', [[2353, 2353], [2355, 2388]], 'legend OHLC + ค่า indicator เหนือกราฟ'),
  m('features/chart/chartControls.js', [[2449, 2611]], 'toolbar กราฟ + วาง/ลบ S/R + เต็มจอ + รายการสัญญาณ'),
  m('features/chart/refreshPrice.js', [[2612, 2659]],
    'ดึงแท่งเทียน + markers แล้ววาดกราฟ — /api/candles, /api/signals/markers, /api/symbol'),
  m('features/watchlist/symbols.js', [[2660, 2687]], 'รายการสัญลักษณ์ — /api/symbols, /api/symbol'),
  m('features/watchlist/watchlist.js', [[2688, 2726]], 'Watchlist ราคาล่าสุด — /api/watchlist'),
  m('features/chart/chartBoot.js', [[2727, 2760]], 'ผูก event กราฟตอน DOMContentLoaded'),
  m('features/status-bar/headerStatus.js', [[2770, 2785], [3243, 3248]],
    'topbar: สัญญาณ ML M1/M5 (/api/ml/latest) + นาฬิกา UTC + session'),
  m('features/ml-signals/feedRow.js', [[2786, 2796]], 'แถวสัญญาณในฟีด "สัญญาณล่าสุด"'),
  m('features/ml-signals/refreshMlTab.js', [[2797, 2845]],
    'แท็บ ML — /api/ml/stats, /api/ml/stats/by_timeframe, /api/ml/signals'),
  m('features/setup-signals/refreshSetupTab.js', [[2846, 2896], [3249, 3249]],
    'แท็บ Rule-Based — /api/stats, /api/stats/by_timeframe, /api/signals'),
  m('features/setup-signals/tickTouchResearch.js', [[2897, 2952]], 'research แตะ EMA200 — /api/ticktouch/stats'),
  m('features/setup-signals/setupCards.js', [[2953, 3041]], 'การ์ด/แถว 11-Checklist (render HTML)'),
  m('features/setup-signals/refreshSetupPanels.js', [[3042, 3082]], 'แผง Setup ทุกคู่เงิน — /api/setup/latest-all'),
  m('features/journal/refreshJournalTab.js', [[3083, 3122]], 'แท็บ Journal — /api/journal/stats, /api/models'),
  m('features/journal/moneyReport.js', [[3123, 3190]], 'รายงาน P&L เงินจริง — /api/journal/report'),
  m('features/journal/drawEquityFull.js', [[3191, 3242]], 'กราฟ Equity Curve เต็มในแท็บ Journal'),
  m('features/journal/journalEvents.js', [[3250, 3284]],
    'ปุ่มช่วงเวลา, บันทึกตั้งค่า (POST /api/journal/settings), Export (/api/journal/export)'),
  m('features/cfd/backtest.js', [[3285, 3362]], 'CFD Backtest — /api/cfd/backtest'),
  m('features/cfd/paperTrading.js', [[3363, 3445]], 'CFD Paper Trading real-time — /api/cfd/paper'),
  m('app/chartLibFallback.js', [[3467, 3475]], 'fallback โหลด lightweight-charts จาก jsdelivr'),
];

export const ARCHIVE_JS = '../_archive/frontend_legacy_canvas_chart.js'; // relative ต่อ frontend/
export const SCRIPT_BLOCK = [1132, 3476]; // <script> … </script> เดิม
