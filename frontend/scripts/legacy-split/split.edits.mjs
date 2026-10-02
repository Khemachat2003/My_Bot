// split.edits.mjs — จุดเดียวที่ "แก้ข้อความ" ระหว่างแยก (กฎ Phase A: ห้าม inline event handler)
// พฤติกรรมเท่าเดิม: ผูกแทนด้วย event delegation ใน src/shared/ui/collapsibles.js
//   data-toggle-parent="open"   = เดิม onclick="this.parentElement.classList.toggle('open')"
//   data-toggle-self="expanded" = เดิม onclick="this.classList.toggle('expanded')"
//   id="btnRunCfdBacktest"      = เดิม onclick="runCFDBacktest()" (ผูกใน features/cfd/backtest.js)
const TOGGLE_PARENT = [`onclick="this.parentElement.classList.toggle('open')"`, `data-toggle-parent="open"`];

export const HTML_EDITS = [
  [894, ...TOGGLE_PARENT], [965, ...TOGGLE_PARENT], [979, ...TOGGLE_PARENT], [1007, ...TOGGLE_PARENT],
  [1026, ...TOGGLE_PARENT], [1052, ...TOGGLE_PARENT], [1074, ...TOGGLE_PARENT], [1098, ...TOGGLE_PARENT],
  [1042, `onclick="runCFDBacktest()"`, `id="btnRunCfdBacktest"`],
];

export const JS_EDITS = [
  [3023, `onclick="this.classList.toggle('expanded')"`, `data-toggle-self="expanded"`],
];

// โค้ดที่ต่อท้าย module (ผูก event แทน inline handler) — ไม่ได้เปลี่ยน logic เดิม
export const JS_APPEND = {
  'features/cfd/backtest.js':
    "// แทน onclick=\"runCFDBacktest()\" เดิมบนปุ่ม Run Backtest\n" +
    "document.getElementById('btnRunCfdBacktest')?.addEventListener('click', () => runCFDBacktest());",
};

// frontend คำนวณเอง → ต้องรายงาน + ติดป้าย TODO (สูตรเดิมไม่แตะ)
export const TODO_NOTES = {
  'shared/lib/indicators.js': 'RSI/ADX/Fractal คำนวณซ้ำฝั่งหน้าเว็บเพื่อวาดกราฟ (สูตรอาจไม่ตรง backend/indicators.py)',
  'features/chart/seriesTransforms.js': 'EMA/SMA/Bollinger คำนวณฝั่งหน้าเว็บเพื่อวาดกราฟ',
  'shared/lib/equityData.js': 'ประกอบ equity curve (capital + equity*stake, cumulative pnl ของ CFD, base 5000) ฝั่งหน้าเว็บ',
  'features/cfd/paperTrading.js': 'progress bar Entry→TP2 ของ open trade คำนวณฝั่งหน้าเว็บ',
  'features/overview/refreshOverview.js': 'ค่า base 5000 ของ CFD equity hard-code ฝั่งหน้าเว็บ',
  'features/journal/refreshJournalTab.js': 'ค่า base 5000 ของ CFD equity hard-code ฝั่งหน้าเว็บ',
};
