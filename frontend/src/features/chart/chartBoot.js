// ผูก event กราฟตอน DOMContentLoaded
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2727–2760 แบบ move-only

import { bindChartToolbar } from './chartControls.js';
import { chartInd, drawLWChart, lastCandles } from './drawLwChart.js';
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
  window.addEventListener('resize',()=>{ refreshLWResize(); });
  const _chartPanelEl=document.getElementById('chartPanel');
  if(_chartPanelEl && window.ResizeObserver){
    new ResizeObserver(()=>refreshLWResize()).observe(_chartPanelEl);
  }
});
