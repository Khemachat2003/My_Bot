// วาดกราฟแท่งเทียน + indicator + markers + trade list
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1217–1218, 2087–2094, 2241–2352, 2354, 2389–2448 แบบ move-only

import { _clearPriceLines, _renderLWMarkers, _selLines } from './chartControls.js';
import { _renderLWDefaultLegend } from './chartLegend.js';
import { _candleTime, initLWChart, lwAdx, lwBbL, lwBbM, lwBbU, lwCandle, lwChart, lwEma100, lwEma200, lwEma50, lwNdi, lwPdi, lwRsi, lwSma5, lwVol } from './lwChartInit.js';
import { _bbArr, _emaArr, _normLW, _smaArr } from './seriesTransforms.js';
import { adx, fractal, rsi } from '../../shared/lib/indicators.js';

let lastCandles=[];
let chartInd={bb:true,ema:true,sma5:true,rsi:true,adx:true,fractal:true,vol:false,grip:false};
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
  const indKey=[chartInd.vol,chartInd.ema,chartInd.bb,chartInd.sma5,chartInd.rsi,chartInd.adx,chartInd.fractal].join('');
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
  if(lwCandle) lwCandle.setData(bars);
  if(lwVol){ if(chartInd.vol) lwVol.setData(bars.map(b=>({time:b.time,value:b.volume,color:b.close>=b.open?'rgba(38,166,154,.5)':'rgba(239,83,80,.5)'}))); else lwVol.setData([]); }
  if(chartInd.ema){ if(lwEma50&&lwEma100&&lwEma200){ lwEma50.setData(_emaArr(bars,50)); lwEma100.setData(_emaArr(bars,100)); lwEma200.setData(_emaArr(bars,200)); } }
  else { if(lwEma50)lwEma50.setData([]); if(lwEma100)lwEma100.setData([]); if(lwEma200)lwEma200.setData([]); }
  const bbOn=chartInd.bb&&bars.length>=20;
  if(bbOn&&lwBbU&&lwBbM&&lwBbL){ const bb=_bbArr(bars,20,2); lwBbU.setData(bb.u); lwBbM.setData(bb.m); lwBbL.setData(bb.l); }
  else { if(lwBbU)lwBbU.setData([]); if(lwBbM)lwBbM.setData([]); if(lwBbL)lwBbL.setData([]); }
  if(chartInd.sma5&&bars.length>=5&&lwSma5){ lwSma5.setData(_smaArr(bars,5)); }
  else { if(lwSma5) lwSma5.setData([]); }
  // ── RSI (pane แยก #rsiChart) ──
  window.__lastRsi=window.__lastAdx=window.__lastPdi=window.__lastNdi=null;
  const closesArr=bars.map(b=>b.close);
  if(chartInd.rsi&&bars.length>=16&&lwRsi){
    const rv=rsi(closesArr,14);
    const rdt=bars.map((b,i)=>({time:b.time,value:rv[i]})).filter(d=>d.value!=null);
    lwRsi.setData(rdt); window.__lastRsi=rdt.length?rdt[rdt.length-1].value:null;
  } else { if(lwRsi) lwRsi.setData([]); }
  // ── ADX (pane แยก #adxChart แถวนี้เป็นแถวล่างสุด → มีแกนเวลา) ──
  if(chartInd.adx&&bars.length>=28&&lwAdx){
    const aa=adx(bars.map(b=>b.high),bars.map(b=>b.low),closesArr,14);
    const adt=bars.map((b,i)=>({time:b.time,value:aa.adx[i]})).filter(d=>d.value!=null);
    const pdt=bars.map((b,i)=>({time:b.time,value:aa.pdi[i]})).filter(d=>d.value!=null);
    const ndt=bars.map((b,i)=>({time:b.time,value:aa.ndi[i]})).filter(d=>d.value!=null);
    lwAdx.setData(adt); lwPdi.setData(pdt); lwNdi.setData(ndt);
    window.__lastAdx=adt.length?adt[adt.length-1].value:null;
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
  if(chartInd.fractal&&bars.length>=16){
    const nd=bars.map((b,i)=>({o:b.open,h:b.high,l:b.low,c:b.close,i}));
    fractalMarkers=fractal(nd,7,7).map(p=>({
      time:bars[p.i].time,
      position:p.t==='H'?'aboveBar':'belowBar',
      color:p.t==='H'?'#FF9800':'#26A69A',   // High=ส้ม / Low=เขียว — ใช้สีที่มีอยู่แล้วในระบบ
      shape:p.t==='H'?'arrowDown':'arrowUp',
      text:'',
    }));
  }
  const markerList=[...sigMarkerList,...fractalMarkers].sort((a,b)=>a.time-b.time);
  if(lwCandle) lwCandle.setMarkers(markerList);
  // fitContent เฉพาะครั้งแรก / เปลี่ยน TF / เปลี่ยน symbol — ไม่รบกวน zoom/pan ที่ผู้ใช้ตั้งไว้
  if(isNewView) lwChart.timeScale().fitContent();

  // ── trade list + auto-select open ──
  lwTradeData=(markers||[]).filter(m=>m&&m.ts&&m.price!=null&&m.direction);
  _renderLWMarkers(markers);
  _buildLWData(markers);
  _autoSelectOpen(markers);
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
    try{ const ln=lwCandle.createPriceLine({price:Number(p),color,lineWidth:1,lineStyle:style,title,axisLabelVisible:true}); _selLines.push(ln); }catch(e){}
  };
  add(t.entry,'#D1D4DC',LightweightCharts.LineStyle.Solid,'ENTRY');
  add(t.sl,'#EF5350',LightweightCharts.LineStyle.Dashed,'SL');
  add(t.tp1,'#FF9800',LightweightCharts.LineStyle.Dashed,'TP1');
  add(t.tp2,'#26A69A',LightweightCharts.LineStyle.Dashed,'TP2');
}

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


export { _lwLastBar, _lwLastPrev, chartInd, drawLWChart, lastCandles };
