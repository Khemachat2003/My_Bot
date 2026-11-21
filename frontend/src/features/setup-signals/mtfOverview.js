// MTF สรุป — ภาพรวมทุกไทม์เฟรม (C-13 ตาม demo "สัญญาณหลายไทม์เฟรม")
// คำนวณจริงจาก /api/candles (1m..4h) ทุก TF: แนวโน้ม (EMA50 + ความชัน) + RSI + ADX
// + สัญญาณล่าสุดต่อ TF (จาก /api/signals + /api/ml/signals เดิม — ไม่เพิ่ม endpoint)
// หน้าเว็บโหลดเฉพาะตอน pane เปิด + throttle 25 วิ (กันยิง 6 TF ทุก 5 วิ = ลดโหลด VPS)

import { fetchJSON } from '../../shared/api/client.js';
import { adx, rsi } from '../../shared/lib/indicators.js';
import { _emaArr } from '../chart/seriesTransforms.js';
import { mergeRows } from '../notifications/recentSignalsLog.js';
import { feedRow } from '../ml-signals/feedRow.js';

const TFS = ['1m', '5m', '15m', '30m', '1h', '4h'];
const TF_KEY = { '1m': 'M1', '5m': 'M5', '15m': 'M15', '30m': 'M30', '1h': 'H1', '4h': 'H4' };
let _last = 0;

const _lastOf = (arr) => {
  for (let i = arr.length - 1; i >= 0; i--) if (arr[i] != null && !Number.isNaN(arr[i])) return arr[i];
  return null;
};

function _trendOf(bars) {
  // แนวโน้ม: ราคาเทียบ EMA50 + ความชัน EMA50 (~12 แท่งหลัง) — 3 สถานะแบบ demo
  if (!bars || bars.length < 60) return 'side';
  const last = bars[bars.length - 1];
  const e50 = _emaArr(bars, 50).map((d) => (d && d.value != null ? d.value : null));
  const e = _lastOf(e50);
  const ePrev = e50.length > 12 ? e50[e50.length - 12] : null;
  if (e == null) return 'side';
  const up = last.close > e;
  const slope = ePrev != null ? e - ePrev : 0;
  if (up && slope > 0) return 'up';
  if (!up && slope < 0) return 'dn';
  return 'side';
}

function _trendBadge(t) {
  if (t === 'up') return '<span class="dir-badge call">▲ ขาขึ้น</span>';
  if (t === 'dn') return '<span class="dir-badge put">▼ ขาลง</span>';
  return '<span class="dir-badge wait">○ ไซด์เวย์</span>';
}

async function refreshMtfTab() {
  const pane = document.getElementById('pane-mtf');
  if (!pane || pane.style.display === 'none') return;
  if (Date.now() - _last < 25000) return; // throttle 25 วิ — 6 TF ไม่ยิงทุกรอบ 5 วิ
  _last = Date.now();

  // สัญญาณล่าสุดแยก TF (จาก endpoint เดิม)
  let sigByTf = {};
  try {
    const [st, ml] = await Promise.all([
      fetchJSON('/api/signals?limit=100'),
      fetchJSON('/api/ml/signals?limit=100'),
    ]);
    const put = (tf, t, dir, kind) => {
      if (!tf) return;
      const k = String(tf).toUpperCase();
      if (!sigByTf[k] || String(t || '') > String(sigByTf[k].t)) sigByTf[k] = { t, dir, kind };
    };
    (st || []).forEach((r) => put(r.timeframe, r.signal_time, r.direction, 'RB'));
    (ml || []).forEach((r) => put(r.timeframe, r.signal_time, r.direction, 'ML'));
  } catch (e) { /* ตารางยังแสดงได้แม้ล่าสุดล่ม */ }

  const candleSets = await Promise.all(
    TFS.map((tf) => fetchJSON(`/api/candles?tf=${tf}&count=200`).catch(() => [])),
  );

  const rows = TFS.map((tf, i) => {
    const bars = candleSets[i] || [];
    const closes = bars.map((b) => b.close);
    const rsiV = bars.length >= 16 ? _lastOf(rsi(closes, 14)) : null;
    const adxA = bars.length >= 28 ? adx(bars.map((b) => b.high), bars.map((b) => b.low), closes, 14) : null;
    const adxV = adxA ? _lastOf(adxA.adx || []) : null;
    const trend = _trendOf(bars);
    const price = bars.length ? bars[bars.length - 1].close : null;
    return { tf, trend, rsiV, adxV, price, sig: sigByTf[TF_KEY[tf]] || null };
  });

  // ตาราง
  const body = document.querySelector('#mtfTable tbody');
  if (body) {
    body.innerHTML = rows.map((r) => {
      const rsiTxt = r.rsiV != null ? r.rsiV.toFixed(1) : '–';
      const rsiCls = r.rsiV == null ? 'muted' : (r.rsiV >= 70 ? 'bear' : (r.rsiV <= 30 ? 'bull' : 'muted'));
      const adxTxt = r.adxV != null ? r.adxV.toFixed(1) : '–';
      const adxStrong = r.adxV != null && r.adxV >= 25;
      const sig = r.sig
        ? `<span class="${r.sig.dir === 'CALL' || r.sig.dir === 'BUY' ? 'dir-badge call' : 'dir-badge put'}">${r.sig.dir === 'CALL' || r.sig.dir === 'BUY' ? '▲' : '▼'} ${r.sig.dir}</span>
           <span class="tt-chip">${r.sig.kind}</span>`
        : '<span class="dl-muted">–</span>';
      return `<tr>
        <td><span class="mdl-key">${r.tf}</span></td>
        <td>${_trendBadge(r.trend)}</td>
        <td class="mono" style="color:var(--${rsiCls})">${rsiTxt}</td>
        <td class="mono" style="color:var(--${adxStrong ? 'accent' : 'muted'})">${adxTxt}${adxStrong ? ' · เทรนด์ชัด' : ''}</td>
        <td>${sig}</td>
      </tr>`;
    }).join('');
  }
  const empty = document.getElementById('mtfEmpty');
  if (empty) empty.style.display = rows.length ? 'none' : 'block';

  // hero: ราคาล่าสุด + สรุปภาพรวม + ตัวนับ 3 สถานะ
  const hero = document.getElementById('mtfHero');
  if (hero) {
    const cnt = { up: 0, dn: 0, side: 0 };
    rows.forEach((r) => cnt[r.trend]++);
    const price = rows.length && rows[0].price != null ? rows[0].price : null;
    const label = cnt.dn >= 4 ? 'ขาลงเด่นในกรอบสั้น' : (cnt.up >= 4 ? 'ขาขึ้นเด่นในกรอบสั้น' : 'ภาพรวมผสม');
    const labelCls = cnt.dn >= 4 ? 'put' : (cnt.up >= 4 ? 'call' : 'wait');
    hero.innerHTML = `
      <div class="mtf-price-row">
        <span class="mtf-price">${price != null ? price.toFixed(2) : '–'}</span>
        <span class="dir-badge ${labelCls}">${label}</span>
      </div>
      <div class="mtf-counts">
        <span class="g-chip up">▲ ขาขึ้น ${cnt.up}</span>
        <span class="g-chip">ไซด์เวย์ ${cnt.side}</span>
        <span class="g-chip dn">▼ ขาลง ${cnt.dn}</span>
      </div>`;
  }

  // สัญญาณล่าสุด (ทุกระบบ) — reuse mergeRows + feedRow เดิม
  const recent = document.getElementById('mtfRecent');
  if (recent) {
    try {
      const [st, ml] = await Promise.all([
        fetchJSON('/api/signals?limit=20'),
        fetchJSON('/api/ml/signals?limit=20'),
      ]);
      const list = mergeRows(ml || [], st || []).slice(0, 10);
      recent.innerHTML = list.length ? list.map((r) => feedRow({
        signal_time: r.t, direction: r.dir, entry_price: r.price, confidence: null, result: r.result,
      })).join('') : '<div class="empty">ยังไม่มีสัญญาณ</div>';
    } catch (e) { /* เงียบ */ }
  }
}

export { refreshMtfTab };
