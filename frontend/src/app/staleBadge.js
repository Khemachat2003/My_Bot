// app/staleBadge.js — Data Age / Stale indicator ของ statusbar (Phase C-2, design_system Section 3)
// นับจากเวลาล่าสุดที่ polling สำเร็จ (≥1 endpoint ตอบกลับมาได้)
// - ปกติ (age ≤ 2×REFRESH_MS) → badge ถูกซ่อน (ไม่ปรากฏเลย)
// - เกิน 2×REFRESH_MS → badge สี warn พร้อมเวลาที่ค้าง
const STALE_AFTER_MS = 2 * 5000; // 2× REFRESH_MS (ค่า default — initStaleBadge ตั้งทับได้)

let lastOkAt = 0;
let refreshMs = 5000;
let timer = null;

/** pure logic (unit-test ได้) — คืน null เมื่อปกติ (ซ่อน), เป็นอ็อบเจ็กต์เมื่อ stale */
function staleState(lastOk, now, refreshInterval) {
  if (!lastOk) return null;
  const age = now - lastOk;
  if (age <= refreshInterval * 2) return null;
  return { ageMs: age, sec: Math.round(age / 1000) };
}

function render() {
  const el = document.getElementById('staleBadge');
  if (!el) return;
  const st = staleState(lastOkAt, Date.now(), refreshMs);
  if (!st) {
    el.style.display = 'none';
    return;
  }
  el.style.display = '';
  el.textContent = `ข้อมูลค้าง ${st.sec}s`;
}

/** บันทึกว่ารอบ polling ล่าสุดมีการตอบกลับสำเร็จ */
function markPollSuccess() {
  lastOkAt = Date.now();
  render();
}

function initStaleBadge(ms = 5000) {
  refreshMs = ms;
  timer = setInterval(render, 1000);
  render();
}

const resetLastOkForTest = () => { lastOkAt = 0; };

export { initStaleBadge, markPollSuccess, staleState, resetLastOkForTest };