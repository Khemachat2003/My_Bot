// fallback โหลด lightweight-charts จาก jsdelivr
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3467–3475 แบบ move-only

import { drawLWChart, lastCandles, refreshPrice } from '../features/chart/index.js';

// ── fallback: ถ้า CDN หลัก (unpkg) โหลดไม่ได้ → ลอง jsdelivr แทน กันกราฟ/ปุ่มตายทั้งหน้า ──
if(!window.LightweightCharts && !window.__lwFallback){
  window.__lwFallback=true;
  const _bs=document.createElement('script');
  _bs.src='https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js';
  _bs.onload=()=>{ try{ if(lastCandles&&lastCandles.length) drawLWChart(lastCandles,window._signalMarkers||[]); else refreshPrice(); }catch(e){ console.error('LW fallback draw fail',e); } };
  _bs.onerror=()=>{ const c=document.getElementById('candleChart'); if(c&&!c.querySelector('canvas')) c.innerHTML='<div class="lw-fallback-msg">โหลดไลบรารีกราฟไม่สำเร็จ — ตรวจการเชื่อมต่อแล้วรีเฟรชใหม่</div>'; };
  document.head.appendChild(_bs);
}
