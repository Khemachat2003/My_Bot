// หน้า Log/Alert — sub-tab "ประวัติสัญญาณ": รวมสัญญาณล่าสุดจาก /api/ml/signals + /api/signals
// (Phase C-2 — เฉพาะข้อมูลจริง ไม่มีสถานะการส่ง Telegram / ไม่มี system log — design_system Section 7)
// (C-6 — ปรับเฉพาะหน้าตาตาม design_system 5.4: คอลัมน์ทิศเปลี่ยนเป็น badge แบบเดียวกับตารางหลัก C-4
//  — คง mergeRows/sort/slice เดิมทุกค่า ไม่แตะโครงข้อมูล/API)
import { fetchJSON } from '../../shared/api/client.js';
import { fmtTime } from '../../shared/lib/formatTime.js';

function pill(result) {
  return `<span class="pill ${result || 'PENDING'}">${result || 'PENDING'}</span>`;
}

// badge ทิศทาง — markup เดียวกับ dirBadge ของตารางหลัก (shared/lib/signalRows.js, CSS .dir-badge ใน tables.css)
// ต่างกันตรงที่แถว log เจอ BUY/SELL ได้ (จาก API เดิม) → โชว์ทิศจริงคู่ ▲/▼ ตามเดิม, ทิศอื่น/ขาด → ○ รอ แบบตารางหลัก
function dirBadge(d) {
  if (d === 'CALL' || d === 'BUY') return `<span class="dir-badge call">▲ ${d}</span>`;
  if (d === 'PUT' || d === 'SELL') return `<span class="dir-badge put">▼ ${d}</span>`;
  return '<span class="dir-badge wait">○ รอ</span>';
}

function mergeRows(ml, setup) {
  const rows = [
    ...ml.map((r) => ({
      t: r.signal_time,
      kind: 'ML',
      dir: r.direction,
      price: r.entry_price,
      strength: r.confidence != null ? (r.confidence * 100).toFixed(1) + '%' : '–',
      result: r.result,
    })),
    ...setup.map((r) => ({
      t: r.signal_time,
      kind: 'Setup',
      dir: r.direction,
      price: r.entry_price,
      strength: r.score != null ? `${r.score.toFixed(1)}/${r.total ?? '–'}` : '–',
      result: r.result,
    })),
  ];
  rows.sort((a, b) => String(b.t || '').localeCompare(String(a.t || '')));
  return rows.slice(0, 100);
}

async function refreshRecentSignalsLog() {
  try {
    const [ml, setup] = await Promise.allSettled([
      fetchJSON('/api/ml/signals?limit=100'),
      fetchJSON('/api/signals?limit=100'),
    ]);
    const mlRows = ml.status === 'fulfilled' ? ml.value : [];
    const setupRows = setup.status === 'fulfilled' ? setup.value : [];
    const body = document.querySelector('#sigLogTable tbody');
    const empty = document.getElementById('sigLogEmpty');
    if (!body) return;
    const rows = mergeRows(mlRows, setupRows);
    if (!rows.length) {
      body.innerHTML = '';
      if (empty) empty.style.display = 'block';
      return;
    }
    if (empty) empty.style.display = 'none';
    body.innerHTML = rows.map((r) => `<tr>
      <td>${fmtTime(r.t)}</td>
      <td><b>${r.kind}</b></td>
      <td>${dirBadge(r.dir)}</td>
      <td class="mono">${r.price != null ? r.price.toFixed(2) : '–'}</td>
      <td class="mono">${r.strength}</td>
      <td>${pill(r.result)}</td>
    </tr>`).join('');
  } catch (e) { /* API ล่ม — แผงนี้ว่าง, stale badge (statusbar) จะบอกเอง */ }
}

export { refreshRecentSignalsLog, mergeRows };