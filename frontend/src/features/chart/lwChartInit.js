// สร้างกราฟหลัก + pane Volume/RSI/ADX + sync pan/zoom + resize
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2079–2086, 2095–2194 แบบ move-only

import { bindLWChart } from './chartControls.js';
import { _lwOHLClegend } from './chartLegend.js';

// ═══════════════════════════════════════════════════════
// lightweight-charts (TradingView) candlestick chart
// ═══════════════════════════════════════════════════════
let lwChart=null, lwCandle=null, lwVol=null;
let lwEma50=null,lwEma100=null,lwEma200=null;
let lwBbU=null,lwBbM=null,lwBbL=null,lwSma5=null;
let lwRsi=null,lwAdx=null,lwPdi=null,lwNdi=null,lwRsiBand=null,lwLine=null;
let lwVolC=null,lwRsiC=null,lwAdxC=null,_lwCharts=[];   // multi-pane: instance แยกของ Volume/RSI/ADX
function _candleTime(d){
  if(d.t==null) return 0;
  if(typeof d.t==='number') return Math.floor(d.t);
  if(typeof d.t==='string'){
    const s=d.t.trim().replace(' ','T');
    // มี timezone ติดมาแล้ว (Z หรือ +HH:MM / ±HHMM) → parse ได้ตรงๆ
    let v;
    if(/[Zz]$/.test(s)||/[+-]\d{2}:?\d{2}$/.test(s)) v=Math.floor(new Date(s).getTime()/1000);
    else v=Math.floor(new Date(s+'Z').getTime()/1000); // ไม่มี tz → ถือเป็น UTC
    return Number.isFinite(v)?v:0;
  }
  return 0;
}

function initLWChart(){
  if(!window.LightweightCharts) return null;
  if(lwChart) return;
  const baseOpts={
    layout:{background:{color:'transparent'},textColor:'#8A8F9C',fontFamily:'IBM Plex Mono, monospace',fontSize:10},
    grid:{vertLines:{color:'#1C212C'},horzLines:{color:'#1C212C'}},
    crosshair:{mode:LightweightCharts.CrosshairMode.Normal},
    rightPriceScale:{borderColor:'#2A2E39',minimumWidth:64,scaleMargins:{top:0.06,bottom:0.28}},
    timeScale:{borderColor:'#2A2E39',timeVisible:true,secondsVisible:false,rightOffset:1,barSpacing:7},
    localization:{locale:'th-TH'},
    // C-16 TradingView-like มือถือ: ปัดแนวนอน = เลื่อนเวลา (มีแรงเฉื่อน kinetic)
    // ปัดแนวตั้ง = ไม่แตะแกนราคา (เดิม default vertTouchDrag:true → ลากขึ้น-ลงบนมือถือ
    // แล้วแกนราคาเลื่อนจนกราฟเพี้ยน ไม่ใช่แค่สกรอลล์หน้าเว็บตามที่ผู้ใช้คาด)
    handleScroll:{mouseWheel:true,pressedMouseMove:true,horizTouchDrag:true,vertTouchDrag:false,kineticScroll:{touch:true,mouse:false}},
    handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true,axisDoubleClickReset:true},
  };
  // ── pane ราคาหลัก (ซ่อนแกนเวลา — แกนเวลาจะอยู่ที่แถบ ADX ล่างสุด) ──
  const el=document.getElementById('candleChart'); if(!el) return;
  lwChart=LightweightCharts.createChart(el,{...baseOpts,width:el.clientWidth||300,height:el.clientHeight||320,timeScale:{...baseOpts.timeScale,visible:false},
    // C-8: watermark เฉพาะ pane ราคาหลัก (เหมือนแพลตฟอร์มเทรด) — จางมาก
    watermark:{visible:true, fontSize:40, color:'rgba(255,255,255,0.03)', fontFamily:'Archivo, IBM Plex Sans Thai, sans-serif', text:'XAUUSD'}});
  // C-9 (mockup): volume เป็น overlay ล่าง pane ราคา (แบบ TradingView) — สร้างก่อน candle เพื่อให้ candle วาดทับ
  try{
    lwVol=lwChart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'vol',priceLineVisible:false,lastValueVisible:false});
    lwChart.priceScale('vol').applyOptions({visible:false, scaleMargins:{top:0.82, bottom:0}});
  }catch(e){ console.error('vol overlay fail',e); }
  lwCandle=lwChart.addCandlestickSeries({
    upColor:'#26A69A',downColor:'#EF5350',borderVisible:false,
    wickUpColor:'#26A69A',wickDownColor:'#EF5350',
    // C-12 fix: เดิมใช้ custom formatter คืนค่าดิบ (p=>p) — ค่า float ยาว "0100.111111111111" ถูกวัดบนแกน
    // จนแกนบวม 104-144px กินกราฟ 25-30% · ถอดออกใช้ format ปกติ (auto precision ตามคู่ + comma แบบ TradingView)
  });
  bindLWChart();          // ← เรียกทันทีหลังมี lwChart/lwCandle (ก่อน indicator อื่น) — S/R click ใช้ได้เสมอ
  try{
    lwEma50=lwChart.addLineSeries({color:'#9C6FE0',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
    lwEma100=lwChart.addLineSeries({color:'#787B86',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
    lwEma200=lwChart.addLineSeries({color:'#FF9800',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  }catch(e){ console.error('ema setup fail',e); }
  try{
    lwBbU=lwChart.addLineSeries({color:'rgba(41,98,255,.45)',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,lineStyle:LightweightCharts.LineStyle.Dotted});
    lwBbM=lwChart.addLineSeries({color:'#2962FF',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
    lwBbL=lwChart.addLineSeries({color:'rgba(41,98,255,.45)',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,lineStyle:LightweightCharts.LineStyle.Dotted});
  }catch(e){ console.error('bb setup fail',e); }
  try{ lwSma5=lwChart.addLineSeries({color:'#26C6DA',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false}); }catch(e){ console.error('sma5 setup fail',e); }
  // C-10: กราฟเส้น/พื้นที่ (โหมดมอนิเตอร์) — สไตล์ TradingView ฟ้า + fill จาง, ซ่อนไว้ก่อน (สลับกับแท่งเทียน)
  try{
    lwLine=lwChart.addAreaSeries({lineColor:'#2962FF',lineWidth:2,
      topColor:'rgba(41,98,255,.26)',bottomColor:'rgba(41,98,255,.02)',
      priceLineVisible:false,lastValueVisible:true,crosshairMarkerVisible:true});
    lwLine.applyOptions({visible:false});
  }catch(e){ console.error('line series fail',e); }
  // ── pane RSI — instance แยก มีเส้น 70/30 ของตัวเอง ──
  try{
    const rEl=document.getElementById('rsiChart');
    if(rEl){
      lwRsiC=LightweightCharts.createChart(rEl,{...baseOpts,width:rEl.clientWidth||300,height:rEl.clientHeight||96,timeScale:{...baseOpts.timeScale,visible:false}});
      // C-9 (mockup): แถบแรเงา 30-70 สีม่วงจาง — baseline series ค่าคงที่ 70 (base 30) เส้น/label ทั้งหมดมองไม่เห็น
      try{
        lwRsiBand=lwRsiC.addBaselineSeries({
          baseValue:{type:'price',price:30},
          topFillColor1:'rgba(179,136,255,.09)', topFillColor2:'rgba(179,136,255,.09)',
          bottomFillColor1:'rgba(0,0,0,0)', bottomFillColor2:'rgba(0,0,0,0)',
          lineWidth:1, lineVisible:false, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false,
        });
      }catch(e){ console.error('rsi band fail',e); }
      lwRsi=lwRsiC.addLineSeries({color:'#9C6FE0',lineWidth:1,priceLineVisible:false,lastValueVisible:true,crosshairMarkerVisible:false,priceFormat:{type:'custom',formatter:v=>v==null?'–':v.toFixed(1)}});
      // C-8: ตัด title/axis label ของเส้น 70/30 ออก (เดิมเป็นป้ายทึบทับกราฟ) — เหลือเส้น dotted บาง ๆ
      lwRsi.createPriceLine({price:70,color:'rgba(120,123,134,.35)',lineStyle:LightweightCharts.LineStyle.Dotted,axisLabelVisible:false,title:''});
      lwRsi.createPriceLine({price:30,color:'rgba(120,123,134,.35)',lineStyle:LightweightCharts.LineStyle.Dotted,axisLabelVisible:false,title:''});
    }
  }catch(e){ console.error('rsi pane fail',e); }
  // ── pane ADX — instance แยก มีแกนเวลาแถวล่างสุด + เส้น 20 ──
  try{
    const aEl=document.getElementById('adxChart');
    if(aEl){
      lwAdxC=LightweightCharts.createChart(aEl,{...baseOpts,width:aEl.clientWidth||300,height:aEl.clientHeight||96,timeScale:{...baseOpts.timeScale,visible:true,timeVisible:true}});
      lwAdx=lwAdxC.addLineSeries({color:'#FF9800',lineWidth:1,priceLineVisible:false,lastValueVisible:true,crosshairMarkerVisible:false,priceFormat:{type:'custom',formatter:v=>v==null?'–':v.toFixed(1)}});
      lwPdi=lwAdxC.addLineSeries({color:'#26A69A',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
      lwNdi=lwAdxC.addLineSeries({color:'#EF5350',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
      lwAdx.createPriceLine({price:20,color:'rgba(120,123,134,.35)',lineStyle:LightweightCharts.LineStyle.Dotted,axisLabelVisible:false,title:''});
      lwAdx.createPriceLine({price:25,color:'rgba(120,123,134,.3)',lineStyle:LightweightCharts.LineStyle.Dotted,axisLabelVisible:false,title:''}); // C-9 (mockup)
    }
  }catch(e){ console.error('adx pane fail',e); }
  _lwSyncPanes();   // pan/zoom ของทุกแถบขยับตามกัน
  _lwOHLClegend();
}

// ── sync pan/zoom ข้ามทุกแถบ (ตามแพทเทิร์นใน multi-pane-chart-demo.html) ──
// C-16: + จำกัดขอบขวา (แท่งล่าสุดหลุดจอไม่ได้ — จำกัดตามจำนวนแท่งที่ระบบดึงมาจริง)
//       + ปุ่มลอย "กลับแท่งล่าสุด" แบบ TradingView (โผล่เมื่อเลื่อนดูประวัติ)
//   เดิม: timeScale ปล่อยให้มุมมองเลื่อน/หุบเลยแท่งล่าสุดได้ไม่จำกัด → หุบกราฟแล้ว
//   แท่งล่าสุดฝั่งขวาหลุดออกนอกจอ ทั้งที่ข้อมูลมีแค่ N แท่ง (ตามที่ผู้ใช้รายงาน)
//   หมายเหตุ: ปัญหาที่รุนแรงกว่า (ลากแกนเวลาใต้ pane ADX แล้วกราฟหลักเด้งไปโซนเก่า)
//   แก้ที่ต้นเหตุใน drawLwChart.js — เติม whitespace ให้ทุก pane เริ่ม logical index 0 เหมือนกัน
const LW_RIGHT_PAD=10;   // เผื่อที่ว่างหลังแท่งล่าสุด (หน่วย: แท่ง)
let _lwLastIdx=-1;       // logical index ของแท่งล่าสุด — drawLWChart ตั้งค่าก่อน setData ทุกครั้ง
function setLWBarCount(n){ _lwLastIdx=Number(n)>0?Number(n)-1:-1; }
function _lwGoBtn(show){
  let b=document.getElementById('lwGoLatest');
  if(!b){
    const wrap=document.getElementById('lwWrap'); if(!wrap) return;
    b=document.createElement('button');
    b.id='lwGoLatest'; b.type='button'; b.title='กลับไปที่แท่งล่าสุด';
    b.innerHTML='<i class="ti ti-chevrons-right"></i>';
    b.addEventListener('click',()=>{
      try{ _lwCharts.forEach(c=>c.timeScale().scrollToRealTime()); }catch(e){}
      b.classList.remove('show');
    });
    wrap.appendChild(b);
  }
  b.classList.toggle('show',!!show);
}
function _lwSyncPanes(){
  _lwCharts=[lwChart,lwRsiC,lwAdxC].filter(Boolean);
  let syncing=false;
  _lwCharts.forEach(c=>{
    c.timeScale().subscribeVisibleLogicalRangeChange(range=>{
      if(syncing||!range) return;
      // จำกัดขอบขวา: ขอบขวาของมุมมองเกิน "แท่งล่าสุด + เผื่อ 10 แท่ง" ไม่ได้ —
      // shift ทั้งหน้าต่างกลับ (คง barSpacing เดิม → รู้สึกเหมือน anchor ติดขอบขวาตลอด)
      let target=range;
      if(_lwLastIdx>50){
        const maxTo=_lwLastIdx+LW_RIGHT_PAD;
        if(range.to>maxTo) target={from:range.from-(range.to-maxTo),to:maxTo};
      }
      syncing=true;
      if(target!==range) c.timeScale().setVisibleLogicalRange(target);
      _lwCharts.forEach(o=>{ if(o!==c) o.timeScale().setVisibleLogicalRange(target); });
      syncing=false;
      // C-9: ขยับ position pills ตาม price scale ที่เปลี่ยน (hook จาก drawLwChart)
      if(window.__lwRepill) window.__lwRepill();
      // C-16: ปุ่มลอยโผล่เมื่อขอบขวาของมุมมองอยู่ห่างแท่งล่าสุด (ผู้ใช้กำลังดูประวัติ)
      _lwGoBtn(_lwLastIdx>50 && range.to<_lwLastIdx-6);
    });
  });
}

function refreshLWResize(){
  const map={'candleChart':lwChart,'rsiChart':lwRsiC,'adxChart':lwAdxC};
  // C-8 mobile fix: กัน canvas กว้างเกินจอ (scrollbar/เลย์เอาต์เปลี่ยนทีหลัง) — clamp ด้วย viewport + parent
  const vw=(window.visualViewport&&window.visualViewport.width)||document.documentElement.clientWidth||window.innerWidth||0;
  for(const id in map){
    const el=document.getElementById(id); const c=map[id];
    if(!c||!el) continue;
    const raw=el.clientWidth||0;
    const parent=el.parentElement?el.parentElement.clientWidth:raw;
    const w=Math.floor(Math.min(raw||parent,parent||raw,vw||raw));
    if(w>0){
      const opt={width:w,height:el.clientHeight||460};
      // จอแคบ: ลดฟอนต์แกนราคาให้ label ไม่ชนขอบ/ถูกตัด
      if(w<420) opt.layout={fontSize:9};
      c.applyOptions(opt);
    }
  }
}


export { _candleTime, initLWChart, lwAdx, lwBbL, lwBbM, lwBbU, lwCandle, lwChart, lwEma100, lwEma200, lwEma50, lwLine, lwNdi, lwPdi, lwRsi, lwRsiBand, lwSma5, lwVol, refreshLWResize, setLWBarCount };
// lwVolC ถูกแทนด้วย volume overlay ใน pane ราคา (C-9)
