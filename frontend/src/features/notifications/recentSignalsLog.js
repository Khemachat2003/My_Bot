// หน้า Log/Alert — sub-tab "ประวัติสัญญาณ": รวมสัญญาณล่าสุดจาก /api/ml/signals + /api/signals
// (Phase C-2 — เฉพาะข้อมูลจริง ไม่มีสถานะการส่ง Telegram / ไม่มี system log — design_system Section 7)
import { fetchJSON } from '../../shared/api/client.js';
import { fmtTime } from '../../shared/lib/formatTime.js';

const DIR_ARROW = { CALL: '▲', PUT: '▼', BUY: '▲', SELL: '▼' };

function pill(result) {
  return `<span class="pill ${result || 'PENDING'}">${result || 'PENDING'}</span>`;
}

function dirCell(d) {
  if (!d) return '<td>–</td>';
  const arrow = DIR_ARROW[d] || '';
  const cls = d === 'CALL' || d === 'BUY' ? 'dir-call' : d === 'PUT' || d === 'SELL' ? 'dir-put' : '';
  return `<td class="${cls}">${arrow} ${d}</td>`;
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
      ${dirCell(r.dir)}
      <td class="mono">${r.price != null ? r.price.toFixed(2) : '–'}</td>
      <td class="mono">${r.strength}</td>
      <td>${pill(r.result)}</td>
    </tr>`).join('');
  } catch (e) { /* API ล่ม — แผงนี้ว่าง, stale badge (statusbar) จะบอกเอง */ }
}

export { refreshRecentSignalsLog, mergeRows };