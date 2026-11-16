// Hero Signal Card — สัญญาณปัจจุบัน + นับถอยหลังแท่ง (C-8 ชุด B)
// แหล่งข้อมูลเดียว: /api/ml/latest (endpoint เดิม เดียวกับ gauges/headerStatus — ไม่เพิ่ม endpoint)
// โครงสร้าง: id ทั้งหมดเป็น hero* — render แบบ set-text (ไม่ innerHTML ข้อมูลจริง) เหมือน feature อื่น

import { fetchJSON } from '../../shared/api/client.js';

const pad = (n) => String(n).padStart(2, '0');

// นับถอยหลังถึง boundary ถัดไปของ tf วินาที (M1=60, M5=300) ด้วยนาฬิกาเครื่อง (UTC เทียบเท่า)
function untilCandle(tfSec) {
  const now = Date.now() / 1000;
  const left = tfSec - (now % tfSec);
  return `${pad(Math.floor(left / 60))}:${pad(Math.floor(left % 60))}`;
}

function setDir(el, sig) {
  el.classList.remove('bull', 'bear', 'muted', 'wait');
  if (sig === 'CALL') { el.textContent = '▲ CALL'; el.classList.add('bull'); }
  else if (sig === 'PUT') { el.textContent = '▼ PUT'; el.classList.add('bear'); }
  else { el.textContent = '○ รอสัญญาณ'; el.classList.add('muted', 'wait'); }
}

function render(g, el = {}) {
  if (!g) { el.conf && (el.conf.textContent = '–'); return; }
  const up = Math.round(g.prob_up * 100), dn = Math.round(g.prob_down * 100);
  const conf = Math.round((g.confidence || 0) * 100);
  setDir(el.dir, g.signal);
  el.conf.textContent = conf + '%';
  el.barUp.style.width = Math.min(up, 100) + '%';
  el.barDn.style.width = Math.min(dn, 100) + '%';
  el.upPct.textContent = up + '%';
  el.dnPct.textContent = dn + '%';
  // เกต: confidence >= threshold → ผ่าน (bull) / ไม่ผ่าน (warn) / NEUTRAL → บอกระยะเกต (muted)
  const th = (g.env_threshold != null ? g.env_threshold : g.threshold_used);
  const pass = g.signal !== 'NEUTRAL' && th != null && g.confidence >= th;
  el.gate.className = 'hero-gate ' + (g.signal === 'NEUTRAL' ? 'off' : pass ? 'pass' : 'low');
  const thPct = th != null ? Math.round(th * 100) : null;
  el.gate.textContent = g.signal === 'NEUTRAL'
    ? (thPct != null ? 'เกต ≥' + thPct + '%' : '○ NEUTRAL')
    : pass ? '✓ ผ่านเกต ' + thPct + '%' : 'ต่ำกว่าเกต ' + thPct + '%';
}

async function refreshHero() {
  try {
    const latest = await fetchJSON('/api/ml/latest');
    render(latest['M1'], DOM_M1);
    // แถวรอง M5 — เก็บ text เดียวว่าทิศ/conf อะไร
    const m5 = latest['M5'];
    if (m5) {
      const sig = m5.signal === 'CALL' ? '▲ CALL' : m5.signal === 'PUT' ? '▼ PUT' : '○ NEUTRAL';
      const cls = m5.signal === 'CALL' ? 'bull' : m5.signal === 'PUT' ? 'bear' : 'muted';
      elTextHero('heroM5', `${sig} ${Math.round(m5.confidence * 100)}%`, cls);
    } else elTextHero('heroM5', 'รอข้อมูล', 'muted');
  } catch (e) { /* เงียบเหมือน feature อื่น */ }
}

// helper กัน getElementById ซ้ำ — คล้าย domText แต่อยู่ใน feature (ไม่ import สาย UI ส่วนกลางที่ไม่จำเป็น)
function elTextHero(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = 'h-sub ' + cls;
  el.textContent = text;
}

/* ═══ DOM refs (โมดูลโหลดครั้งเดียว) ═══ */
const DOM_M1 = {
  dir: document.getElementById('heroDir'),
  conf: document.getElementById('heroConf'),
  barUp: document.getElementById('heroBarUp'),
  barDn: document.getElementById('heroBarDn'),
  upPct: document.getElementById('heroUpPct'),
  dnPct: document.getElementById('heroDnPct'),
  gate: document.getElementById('heroGate'),
};

/* countdown ทุกวินาที (นาฬิกาเครื่อง — แท่ง M1/M5 ปิดตรง boundary UTC เป๊ะ) */
function tickCountdown() {
  const m1 = document.getElementById('heroCdM1'), m5 = document.getElementById('heroCdM5');
  if (m1) m1.textContent = untilCandle(60);
  if (m5) m5.textContent = untilCandle(300);
}
tickCountdown();
setInterval(tickCountdown, 1000);
// refreshHero เรียกจาก app/refreshLoop.js ทุก 5 วิ เท่านั้น (ไม่ยิง fetch ซ้ำในโมดูล)

export { refreshHero };
