// ผูก event กราฟตอน DOMContentLoaded
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2727–2760 แบบ move-only

import { bindChartToolbar } from './chartControls.js';
import { chartInd, chartMode, drawLWChart, lastCandles, setChartMode, setChartType } from './drawLwChart.js';
import { lwChart, refreshLWResize } from './lwChartInit.js';
import { refreshPrice } from './refreshPrice.js';
import { loadSymbols } from '../watchlist/index.js';

document.addEventListener('DOMContentLoaded',()=>{
  bindChartToolbar();           // ปุ่มทั้งหมดทำงานทันที แม้ chart ยังไม่โหลด
  loadSymbols();
  document.getElementById('tfGroup')?.addEventListener('click',e=>{
    const btn=e.target.closest('.tf-btn'); if(!btn) return;
    document.querySelectorAll('#tfGroup .tf-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    lwChart&&lwChart.timeScale().fitContent();
    refreshPrice(true);   // ← user action → โชว์ loading
  });
  document.getElementById('chartLegendBar')?.addEventListener('click',e=>{
    const chip=e.target.closest('.lo-chip'); if(!chip) return;
    const key=chip.dataset.ind;
    chartInd[key]=!chartInd[key];
    chip.classList.toggle('off',!chartInd[key]);
    const bar=document.querySelector('#chartIndBar .ind-chip[data-ind="'+key+'"]');
    if(bar) bar.classList.toggle('active',chartInd[key]);
  });
  document.getElementById('lbCollapse')?.addEventListener('click',()=>{
    document.getElementById('chartLegendBar')?.classList.toggle('collapsed');
  });
  document.getElementById('chartIndBar')?.addEventListener('click',e=>{
    const chip=e.target.closest('.ind-chip'); if(!chip) return;
    chip.classList.toggle('active');
    chartInd[chip.dataset.ind]=chip.classList.contains('active');
    if(lastCandles.length) drawLWChart(lastCandles,window._signalMarkers||[]);
  });
  // C-8 mobile fix: resize หลายทาง — window/visualViewport/RO/wrap + re-fit หลังเลย์เอาต์นิ่ง
  // (เดิมวัดก่อน scrollbar ปรากฏ → canvas กว้างเกินจอ ~9-16px ทำให้ price scale ขวาถูกตัด)
  const _refit=()=>requestAnimationFrame(()=>refreshLWResize());
  window.addEventListener('resize',()=>{ _refit(); setTimeout(refreshLWResize,250); });
  if(window.visualViewport) window.visualViewport.addEventListener('resize',_refit);
  const _chartPanelEl=document.getElementById('chartPanel');
  const _lwWrapEl=document.getElementById('lwWrap');
  if(window.ResizeObserver){
    const ro=new ResizeObserver(()=>_refit());
    if(_chartPanelEl) ro.observe(_chartPanelEl);
    if(_lwWrapEl) ro.observe(_lwWrapEl);
  }
  // drawer มือถือเปิด/ปิด = เลย์เอาต์เปลี่ยน (transition .2s) → refit หลังจบ transition
  document.addEventListener('click',(e)=>{
    if(e.target instanceof Element && e.target.closest('#navToggle,#drawerScrim')) setTimeout(refreshLWResize,280);
  });
  // กันพลาดตอนฟอนต์/scrollbar มาช้า
  setTimeout(refreshLWResize,300);
  setTimeout(refreshLWResize,1200);
  // C-9 (mockup): ปุ่ม fx เปิด/ปิดแผงตัวชี้วัด + ขยับ position pills หลัง resize ทุกทาง
  // C-10: ถ้าอยู่โหมดมอนิเตอร์แล้วกด fx → สลับเป็นโหมดวิเคราะห์ให้ก่อน (indicator ถึงจะโชว์)
  document.getElementById('btnFx')?.addEventListener('click',()=>{
    if(chartMode!=='analysis') setChartMode('analysis');
    document.getElementById('chartExtra')?.classList.toggle('open');
  });
  // C-10: ปุ่มสลับโหมด + ชนิดกราฟ
  document.getElementById('btnMode')?.addEventListener('click',()=>{
    setChartMode(chartMode==='analysis'?'monitor':'analysis');
  });
  document.getElementById('btnTypeLine')?.addEventListener('click',()=>setChartType('line'));
  document.getElementById('btnTypeCandle')?.addEventListener('click',()=>setChartType('candle'));
  // C-11: เครื่องมือรอง (มือถือ) — popover ทับกราฟ + คลิกข้างนอกปิดเอง
  const _tp=document.getElementById('toolsPop');
  document.getElementById('btnTools')?.addEventListener('click',(e)=>{
    e.stopPropagation();
    _tp?.classList.toggle('open');
  });
  document.addEventListener('click',(e)=>{
    if(!_tp||!_tp.classList.contains('open')) return;
    const t=e.target instanceof Element?e.target:null;
    if(t&&(_tp.contains(t)||t.closest('#btnTools'))) return;
    _tp.classList.remove('open');
  });
  const _repill=()=>{ if(window.__lwRepill) window.__lwRepill(); };
  window.addEventListener('resize',()=>setTimeout(_repill,60));
});
