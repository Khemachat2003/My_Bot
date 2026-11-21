// วาดกราฟแท่งเทียน + indicator + markers + trade list
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1217–1218, 2087–2094, 2241–2352, 2354, 2389–2448 แบบ move-only

import { _clearPriceLines, _renderLWMarkers, _selLines } from './chartControls.js';
import { _renderLWDefaultLegend } from './chartLegend.js';
import { _candleTime, initLWChart, lwAdx, lwBbL, lwBbM, lwBbU, lwCandle, lwChart, lwEma100, lwEma200, lwEma50, lwLine, lwNdi, lwPdi, lwRsi, lwRsiBand, lwSma5, lwVol, refreshLWResize } from './lwChartInit.js';
import { _bbArr, _emaArr, _normLW, _smaArr } from './seriesTransforms.js';
import { adx, fractal, rsi } from '../../shared/lib/indicators.js';

let lastCandles=[];
let chartInd={bb:true,ema:true,sma5:true,rsi:true,adx:true,fractal:true,vol:true,grip:false}; // C-9: vol overlay เปิด default

// ═══ C-10: โหมดมอนิเตอร์/วิเคราะห์ + ชนิดกราฟ เส้น/แท่ง (จำค่าไว้ใน localStorage) ═══
// มอนิเตอร์ (default) = กราฟเส้นสบายตา ไม่มี indicator/RSI/ADX/volume — ดูคร่าว ๆ แบบ TradingView
// วิเคราะห์ = แท่งเทียน + EMA/BB/SMA + volume + RSI/ADX pane + fractal ตาม chartInd เดิม
let chartMode='monitor', chartType='line';
try{
  const _m=localStorage.getItem('lwMode'); if(_m==='analysis'||_m==='monitor') chartMode=_m;
  const _t=localStorage.getItem('lwType'); if(_t==='line'||_t==='candle') chartType=_t;
}catch(e){}
function setChartMode(m){
  if(m!=='monitor'&&m!=='analysis') return;
  chartMode=m; try{localStorage.setItem('lwMode',m);}catch(e){}
  _applyModeDom();
  if(lastCandles.length) drawLWChart(lastCandles,window._signalMarkers||[]);
}
function setChartType(t){
  if(t!=='line'&&t!=='candle') return;
  chartType=t; try{localStorage.setItem('lwType',t);}catch(e){}
  if(lastCandles.length) drawLWChart(lastCandles,window._signalMarkers||[]);
}
function _applyModeDom(){
  const ana=chartMode==='analysis';
  const rsi=document.getElementById('lwPaneRsi'), adx=document.getElementById('lwPaneAdx');
  if(rsi) rsi.style.display=ana?'':'none';
  if(adx) adx.style.display=ana?'':'none';
  const panel=document.getElementById('chartPanel');
  if(panel) panel.classList.toggle('monitor',!ana);
  // มอนิเตอร์: ADX (แกนเวลา) ถูกซ่อน → เปิดแกนเวลาที่ pane หลักแทน
  try{ if(lwChart) lwChart.applyOptions({timeScale:{visible:!ana}}); }catch(e){}
  // ปุ่มโหมด = บอกปลายทาง (อยู่มอนิเตอร์ → เขียน "วิเคราะห์")
  const btn=document.getElementById('btnMode');
  if(btn) btn.innerHTML=ana?'<i class="ti ti-eye"></i><span class="btn-lbl">มอนิเตอร์</span>':'<i class="ti ti-focus-2"></i><span class="btn-lbl">วิเคราะห์</span>';
  const bL=document.getElementById('btnTypeLine'), bC=document.getElementById('btnTypeCandle');
  if(bL) bL.classList.toggle('active',chartType==='line');
  if(bC) bC.classList.toggle('active',chartType==='candle');
  refreshLWResize();
}
let lwSrLines=[];
let lwActiveLines=[];
let lwAddingSr=false;
let lwTradeData=[];
let _lwFitKey='';   // จำ TF+symbol → fitContent เฉพาะตอนเปลี่ยน
let _lwLastSig=null; // จำแท่งท้ายสุด+สัญญาณ → ข้าม redraw ซ้ำตอน refresh
let _lwPrevCount=0;  // จำจำนวนแท่งก่อนหน้า → กันข้อมูลหายชั่วคราวทำให้กราฟหดเหลือ 1-2 แท่ง

// TF → วินาทีต่อแท่ง (สำหรับ snap marker ให้ตรงกับเวลาเปิดแท่งเทียน)
const _TF_SECONDS={'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600,'4h':14400};

function drawLWChart(prices,markers,tf){
  if(!window.LightweightCharts){ return; }
  lastCandles=prices||[];  // sync ไว้ → ปุ่ม toggle indicator (#chartIndBar) redraw ได้ทันทีโดยไม่ต้องรอ refresh รอบหน้า
  const bars=_normLW(prices);
  if(!bars.length) return;
  initLWChart();
  const needInit=!lwCandle;
  const sym=document.getElementById('chartSymbol')?.value||'';
  const fitKey=tf+'|'+sym;
  const isNewView=fitKey!==_lwFitKey;
  if(isNewView) _lwFitKey=fitKey;
  // ข้ามงานซ้ำถ้าแท่งท้ายสุด (เวลา+close)+สัญญาณ+การตั้งค่า indicator ไม่เปลี่ยน → ลดกระตุกตอน refresh ทุก 5 วิ
  const last=bars[bars.length-1];
  const ana=chartMode==='analysis';
  const indKey=chartMode+chartType+[chartInd.vol,chartInd.ema,chartInd.bb,chartInd.sma5,chartInd.rsi,chartInd.adx,chartInd.fractal].join('');
  if(!needInit&&!isNewView&&_lwLastSig&&_lwLastSig.t===last.time&&_lwLastSig.c===last.close&&_lwLastSig.sig===JSON.stringify(markers||[])&&_lwLastSig.ind===indKey){
    return;
  }
  // กัน "ข้อมูลหายชั่วคราว" (Deriv ตอบไม่ครบ) ทำให้กราฟที่วาดดีแล้วหดเหลือ 1-2 แท่ง
  if(!needInit&&!isNewView&&_lwPrevCount>100&&bars.length<30&&bars.length<_lwPrevCount/3){
    const vEl=document.getElementById('lbValues');
    if(vEl) vEl.innerHTML='<span class="v-m">ข้อมูลแท่งไม่ครบ ('+bars.length+' แท่ง) — กรุณารอ refresh ถัดไป</span>';
    return;
  }
  _lwLastSig={t:last.time,c:last.close,sig:JSON.stringify(markers||[]),tf:tf||'',ind:indKey};
  _lwPrevCount=bars.length;
  _lwLastBar=bars[bars.length-1];
  _lwLastPrev=bars.length>1?bars[bars.length-2].close:null;
  _renderLWDefaultLegend();
  // C-10: มอนิเตอร์ = เส้นพื้นที่เดียวสบายตา · วิเคราะห์ = แท่งเทียน + ทุก indicator ตาม chartInd
  if(lwCandle){ lwCandle.setData(bars); lwCandle.applyOptions({visible:chartType==='candle'}); }
  if(lwLine){ lwLine.setData(bars.map(b=>({time:b.time,value:b.close}))); lwLine.applyOptions({visible:chartType==='line'}); }
  if(lwVol){ if(ana&&chartInd.vol) lwVol.setData(bars.map(b=>({time:b.time,value:b.volume,color:b.close>=b.open?'rgba(38,166,154,.42)':'rgba(239,83,80,.42)'}))); else lwVol.setData([]); }
  if(ana&&chartInd.ema){ if(lwEma50&&lwEma100&&lwEma200){ lwEma50.setData(_emaArr(bars,50)); lwEma100.setData(_emaArr(bars,100)); lwEma200.setData(_emaArr(bars,200)); } }
  else { if(lwEma50)lwEma50.setData([]); if(lwEma100)lwEma100.setData([]); if(lwEma200)lwEma200.setData([]); }
  const bbOn=ana&&chartInd.bb&&bars.length>=20;
  if(bbOn&&lwBbU&&lwBbM&&lwBbL){ const bb=_bbArr(bars,20,2); lwBbU.setData(bb.u); lwBbM.setData(bb.m); lwBbL.setData(bb.l); }
  else { if(lwBbU)lwBbU.setData([]); if(lwBbM)lwBbM.setData([]); if(lwBbL)lwBbL.setData([]); }
  if(ana&&chartInd.sma5&&bars.length>=5&&lwSma5){ lwSma5.setData(_smaArr(bars,5)); }
  else { if(lwSma5) lwSma5.setData([]); }
  // ── RSI (pane แยก #rsiChart) ──
  window.__lastRsi=window.__lastAdx=window.__lastPdi=window.__lastNdi=null;
  const closesArr=bars.map(b=>b.close);
  // C-10 fix: RSI/ADX ต้องเติมข้อมูลเสมอ (แม้โหมดมอนิเตอร์จะซ่อน pane) —
  // ถ้า setData([]) ตอนซ่อน sync ข้าม pane จะดึง range กราฟหลักให้หดเหลือไม่กี่แท่ง
  if(chartInd.rsi&&bars.length>=16&&lwRsi){
    const rv=rsi(closesArr,14);
    const rdt=bars.map((b,i)=>({time:b.time,value:rv[i]})).filter(d=>d.value!=null);
    lwRsi.setData(rdt); window.__lastRsi=ana&&rdt.length?rdt[rdt.length-1].value:null;
    // C-9 (mockup): band แรเงา 30-70 ลากตามช่วงเวลาเดียวกับ RSI (ค่าคงที่ 70)
    if(lwRsiBand) lwRsiBand.setData(bars.map(b=>({time:b.time,value:70})));
  } else { if(lwRsi) lwRsi.setData([]); if(lwRsiBand) lwRsiBand.setData([]); }
  // ── ADX (pane แยก #adxChart แถวนี้เป็นแถวล่างสุด → มีแกนเวลา) ──
  if(chartInd.adx&&bars.length>=28&&lwAdx){
    const aa=adx(bars.map(b=>b.high),bars.map(b=>b.low),closesArr,14);
    const adt=bars.map((b,i)=>({time:b.time,value:aa.adx[i]})).filter(d=>d.value!=null);
    const pdt=bars.map((b,i)=>({time:b.time,value:aa.pdi[i]})).filter(d=>d.value!=null);
    const ndt=bars.map((b,i)=>({time:b.time,value:aa.ndi[i]})).filter(d=>d.value!=null);
    lwAdx.setData(adt); lwPdi.setData(pdt); lwNdi.setData(ndt);
    window.__lastAdx=ana&&adt.length?adt[adt.length-1].value:null;
    window.__lastPdi=pdt.length?pdt[pdt.length-1].value:null;
    window.__lastNdi=ndt.length?ndt[ndt.length-1].value:null;
  } else { if(lwAdx){ lwAdx.setData([]); lwPdi.setData([]); lwNdi.setData([]); } }
  _renderLWDefaultLegend();   // ← เรียกซ้ำหลังได้ค่า RSI/ADX ล่าสุด → legend แสดงทันที

  // ── Markers: shape=ทิศทาง, color=ระบบ — สัญญาณเกิดกลางแท่ง → snap ลงไปที่แท่งที่เปิดก่อนหน้า
  const activeTf=document.querySelector('#tfGroup .tf-btn.active')?.dataset.tf||tf||'1m';
  const intSec=_TF_SECONDS[String(activeTf)]||300;
  const tsSet=new Set(bars.map(b=>b.time));
  const barTimes=[...tsSet].sort((a,b)=>a-b);
  const snapToBar=ts=>{
    const t=_candleTime(ts); if(!t) return null;
    const slot=Math.floor(t/intSec)*intSec;
    let cand=tsSet.has(slot)?slot:null;
    // เผื่อ series เริ่มไม่ตรง 0 → หาแท่งที่เปิดในหน้าต่างเดียวกับสัญญาณ
    for(const bt of barTimes){
      if(bt>=slot&&bt<slot+intSec){ cand=bt; break; }
    }
    return cand;
  };
  const sigMarkerList=(markers||[]).filter(m=>m&&m.ts&&m.price!=null&&m.direction).map(m=>{
    const barTime=snapToBar(m); if(barTime==null) return null;
    const sysLabel=m.type==='ML'?'ML':m.importance===1?'IMP1':m.importance===2?'IMP2':'RBF';
    // design_system C-3: สี marker = ทิศทาง (bull/bear) + รูปทรง ▲▼ — ตัดสีม่วง/น้ำเงินแยก ML/RB
    // ระบบต้นทางบอกด้วยข้อความบน marker (ML/IMP1/IMP2/RBF) เสมอ (canvas ไม่รองรับ var() → ใช้ hex ของ token)
    const color=m.direction==='CALL'?'#16C784':'#F0465C';
    return {
      time:barTime,
      position:m.direction==='CALL'?'belowBar':'aboveBar',
      color,
      shape:m.direction==='CALL'?'arrowUp':'arrowDown',
      text:sysLabel+' '+m.direction,
    };
  }).filter(Boolean);
  // ── Fractal 15: จุดสูง=ส้ม(แนวต้าน) · จุดต่ำ=เขียว(แนวรับ) — ไม่ซ้ำกับสัญญาณ ──
  let fractalMarkers=[];
  if(ana&&chartInd.fractal&&bars.length>=16){ // C-10: fractal จุดสบายตาเฉพาะโหมดวิเคราะห์
    const nd=bars.map((b,i)=>({o:b.open,h:b.high,l:b.low,c:b.close,i}));
    fractalMarkers=fractal(nd,7,7).map(p=>({
      time:bars[p.i].time,
      position:p.t==='H'?'aboveBar':'belowBar',
      color:p.t==='H'?'#FF9800':'#26A69A',   // High=ส้ม / Low=เขียว — ใช้สีที่มีอยู่แล้วในระบบ
      shape:p.t==='H'?'arrowDown':'arrowUp',
      text:'',
    }));
  }
  // C-10: marker ไปตาม series ที่กำลังแสดง (เส้น/แท่ง) — สัญญาณ ▲▼ โชว์ทุกโหมด (นี่คือหัวใจของ monitor)
  const markerList=[...sigMarkerList,...fractalMarkers].sort((a,b)=>a.time-b.time);
  const targetSeries=chartType==='line'?lwLine:lwCandle;
  if(targetSeries) targetSeries.setMarkers(markerList);
  // fitContent เฉพาะครั้งแรก / เปลี่ยน TF / เปลี่ยน symbol — ไม่รบกวน zoom/pan ที่ผู้ใช้ตั้งไว้
  if(isNewView) lwChart.timeScale().fitContent();

  // ── trade list + auto-select open ──
  lwTradeData=(markers||[]).filter(m=>m&&m.ts&&m.price!=null&&m.direction);
  _renderLWMarkers(markers);
  _buildLWData(markers);
  _autoSelectOpen(markers);
  // C-9: หลัง redraw (fit/scale เปลี่ยน) → ขยับ pills ให้ตรงเส้น
  _renderPills();
  // C-10: ซิงก์ DOM โหมด/ปุ่ม (ครั้งแรกหลัง chart init)
  _applyModeDom();
}

let _lwLastBar=null,_lwLastPrev=null;
// ── trade list (คลิกเพื่อดู SL/TP เฉพาะรายการ) ──
function _buildLWData(markers){
  const rowsEl=document.getElementById('lwTradeRows'); if(!rowsEl) return;
  lwTradeData=markers||[];
  const items=lwTradeData.map((m,rowIdx)=>{
    let entry=m.price!=null?Number(m.price):null;
    let sl=null,tp1=null,tp2=null,res=m.result||(m.cfd&&m.cfd.cfd_result);
    if(m.cfd){ if(entry==null) entry=m.cfd.effective_entry; sl=m.cfd.sl; tp1=m.cfd.tp1; tp2=m.cfd.tp2; }
    if(m.cfd&&m.cfd.cfd_result===null&&res==='PENDING') entry=m.cfd.effective_entry||entry;
    return {rowIdx,ts:m.ts,entry,sl,tp1,tp2,result:m.type==='ML'?'ML':(m.importance===1?'IMP1':m.importance===2?'IMP2':'RBF'),direction:m.direction,res,
            price:m.price,open:res==='PENDING'};
  }).filter(t=>t.ts);
  rowsEl.innerHTML=items.map(t=>{
    const ent=(t.entry!=null?Number(t.entry).toFixed(2):'–');
    const cls=t.open?'lw-trow open':'lw-trow';
    const sc=t.direction==='CALL'?'up':'down';
    return `<div class="${cls}" data-t="${(t.ts||'').replace ? String(t.ts) : t.ts}">
      <span class="dir" style="color:${t.direction==='CALL'?'#26A69A':'#EF5350'}">${t.direction}</span>
      <span class="lbl">${t.result}</span>
      <span class="sub">${ent}</span>${t.open?'<span class="tag open">OPEN</span>':(t.res?'<span class="tag">'+t.res+'</span>':'<span class="tag"></span>')}
    </div>`;
  }).join('') || '<div class="lw-empty">ยังไม่มี trade</div>';
  rowsEl.querySelectorAll('.lw-trow').forEach(row=>{
    row.addEventListener('click',()=>{
      document.querySelectorAll('.lw-trow').forEach(r=>r.classList.remove('sel'));
      row.classList.add('sel');
      const t=lwTradeData.find(x=>String(x.ts)===row.dataset.t);
      _showTrade(t);
    });
  });
}

function _showTrade(t){
  if(!t||!lwCandle){ return; }
  _clearPriceLines();
  const add=(p,color,style,title)=>{
    if(p==null) return;
    // C-12: ปัดทศนิยม 2 ตำแหน่ง — เดิมราคา 5 ตำแหน่ง (3573.50000) ทำ label แกนยาว 104px กินกราฟ ~30%
    const px=Math.round(Number(p)*100)/100;
    try{ const ln=lwCandle.createPriceLine({price:px,color,lineWidth:1,lineStyle:style,title,axisLabelVisible:true}); _selLines.push(ln); }catch(e){}
  };
  // C-12: แกนราคาไม่ใส่ title (เดิม ENTRY/SL/TP1/TP2 ทำแกนบวมเป็น 104-144px กินกราฟ 25-30%)
  // — บอกชื่อเส้นด้วย pills บนกราฟแทน (แบบ TradingView แกนมีแต่ตัวเลขสี)
  add(t.entry,'#D1D4DC',LightweightCharts.LineStyle.Solid,'');
  add(t.sl,'#EF5350',LightweightCharts.LineStyle.Dashed,'');
  add(t.tp1,'#FF9800',LightweightCharts.LineStyle.Dashed,'');
  add(t.tp2,'#26A69A',LightweightCharts.LineStyle.Dashed,'');
  // C-9 (mockup): position pills สีทับเส้น ENTRY/SL/TP ที่เลือก — ขยับตาม price scale ผ่าน window.__lwRepill
  _pillData=[];
  if(t.entry!=null) _pillData.push({price:Number(t.entry),kind:'entry',
    text:`${t.direction==='CALL'?'▲':'▼'} ENTRY ${Number(t.entry).toFixed(2)}`});
  if(t.sl!=null) _pillData.push({price:Number(t.sl),kind:'sl',text:`SL − ${Number(t.sl).toFixed(2)}`});
  if(t.tp1!=null) _pillData.push({price:Number(t.tp1),kind:'tp',text:`TP1 + ${Number(t.tp1).toFixed(2)}`});
  if(t.tp2!=null) _pillData.push({price:Number(t.tp2),kind:'tp',text:`TP2 + ${Number(t.tp2).toFixed(2)}`});
  _renderPills();
}

let _pillData=[];
function _renderPills(){
  const wrap=document.querySelector('.chart-wrap');
  if(!wrap||!lwCandle){ return; }
  let el=document.getElementById('posPills');
  if(!_pillData.length){ if(el) el.remove(); return; }
  if(!el){ el=document.createElement('div'); el.id='posPills'; el.className='pos-pills'; wrap.appendChild(el); }
  el.innerHTML=_pillData.map(p=>{
    const y=lwCandle.priceToCoordinate(p.price);
    if(y==null) return '';
    return `<span class="pos-pill ${p.kind}" style="top:${Math.round(y-9)}px">${p.text}</span>`;
  }).join('');
}
window.__lwRepill=_renderPills;

function _autoSelectOpen(markers){
  const rowsEl=document.getElementById('lwTradeRows'); if(!rowsEl) return;
  const openMarker=(markers||[]).find(m=>(m.result==='PENDING')||(m.cfd&&m.cfd.cfd_result==='PENDING'));
  let target=null;
  if(openMarker){
    const row=rowsEl.querySelector(`.lw-trow[data-t="${String(openMarker.ts)}"]`);
    if(row){ target=row; }
  }
  if(!target){ target=rowsEl.querySelector('.lw-trow'); }
  if(target){
    target.classList.add('sel');
    _showTrade(lwTradeData.find(x=>String(x.ts)===target.dataset.t));
  }
}


export { _lwLastBar, _lwLastPrev, chartInd, chartMode, chartType, setChartMode, setChartType, drawLWChart, lastCandles };
