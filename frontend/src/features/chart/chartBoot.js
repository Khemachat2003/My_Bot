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
    // C-11b: sync ชื่อ TF บนปุ่ม dropdown + ปิด popover หลังเลือก (มือถือ)
    const cur=document.getElementById('tfCur'); if(cur) cur.textContent=btn.dataset.tf||'';
    document.getElementById('tfPop')?.classList.remove('open');
    lwChart&&lwChart.timeScale().fitContent();
    refreshPrice(true);   // ← user action → โชว์ loading
  });
  document.getElementById('chartLegendBar')?.addEventListener('click',e=>{
    const chip=e.target.closest('.lo-chip'); if(!chip) return;
    const key=chip.dataset.ind;
    chartInd[key]=!chartInd[key];
    chip.classList.toggle('off',!chartInd[key]);
    const bar=document.querySelector('.chart-extra .ind-row[data-ind="'+key+'"]');
    if(bar) bar.classList.toggle('on',chartInd[key]);
    _updIndCount();
  });
  document.getElementById('lbCollapse')?.addEventListener('click',()=>{
    document.getElementById('chartLegendBar')?.classList.toggle('collapsed');
  });
  // C-13 (demo): chips อยู่ 2 กลุ่ม (บนกราฟ/แผงย่อย) → delegate ที่ #chartExtra จุดเดียว
  const _updIndCount=()=>{
    const rows=[...document.querySelectorAll('.chart-extra .ind-row')];
    const on=rows.filter(r=>r.classList.contains('on')).length;
    const el=document.getElementById('indCount');
    if(el) el.textContent=`เปิดใช้งาน ${on}/${rows.length}`;
  };
  document.getElementById('chartExtra')?.addEventListener('click',e=>{
    const row=e.target.closest('.ind-row'); if(!row) return;
    row.classList.toggle('on');
    chartInd[row.dataset.ind]=row.classList.contains('on');
    _updIndCount();
    if(lastCandles.length) drawLWChart(lastCandles,window._signalMarkers||[]);
  });
  _updIndCount();
  // รีเซ็ตเป็นค่าเริ่มต้น (demo: ปุ่มใน bottom sheet)
  document.getElementById('btnIndReset')?.addEventListener('click',()=>{
    Object.assign(chartInd,{ema:true,bb:true,sma5:true,rsi:true,adx:true,fractal:true,vol:true,grip:false});
    document.querySelectorAll('.chart-extra .ind-row').forEach(r=>r.classList.toggle('on',!!chartInd[r.dataset.ind]));
    _updIndCount();
    if(lastCandles.length) drawLWChart(lastCandles,window._signalMarkers||[]);
  });
  // เสร็จสิ้น = ปิด sheet/แผง
  const _indClose=()=>document.getElementById('chartExtra')?.classList.remove('open');
  document.getElementById('btnIndDone')?.addEventListener('click',_indClose);
  document.getElementById('btnIndClose')?.addEventListener('click',_indClose);
  // คลิกข้างนอก = ปิด (สะดวกทั้ง sheet มือถือและแผง desktop)
  document.addEventListener('click',(e)=>{
    const ex=document.getElementById('chartExtra');
    if(!ex||!ex.classList.contains('open')) return;
    const t=e.target instanceof Element?e.target:null; if(!t) return;
    if(ex.contains(t)||t.closest('#btnFx')) return;
    ex.classList.remove('open');
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
  // C-11: เครื่องมือรอง + TF (มือถือ) — popover ทับกราฟ + คลิกข้างนอกปิดเอง
  const _tp=document.getElementById('toolsPop');
  const _fp=document.getElementById('tfPop');
  document.getElementById('btnTools')?.addEventListener('click',(e)=>{
    e.stopPropagation();
    _fp?.classList.remove('open');
    _tp?.classList.toggle('open');
  });
  document.getElementById('btnTf')?.addEventListener('click',(e)=>{
    e.stopPropagation();
    _tp?.classList.remove('open');
    _fp?.classList.toggle('open');
  });
  document.addEventListener('click',(e)=>{
    const t=e.target instanceof Element?e.target:null;
    if(!t) return;
    if(_tp&&_tp.classList.contains('open')&&!_tp.contains(t)&&!t.closest('#btnTools')) _tp.classList.remove('open');
    if(_fp&&_fp.classList.contains('open')&&!_fp.contains(t)&&!t.closest('#btnTf')) _fp.classList.remove('open');
  });
  const _repill=()=>{ if(window.__lwRepill) window.__lwRepill(); };
  window.addEventListener('resize',()=>setTimeout(_repill,60));
});
