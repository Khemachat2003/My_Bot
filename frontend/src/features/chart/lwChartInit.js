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
let lwRsi=null,lwAdx=null,lwPdi=null,lwNdi=null;
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
    layout:{background:{color:'transparent'},textColor:'#787B86',fontFamily:'IBM Plex Mono, monospace'},
    grid:{vertLines:{color:'#1E222D'},horzLines:{color:'#1E222D'}},
    crosshair:{mode:LightweightCharts.CrosshairMode.Normal},
    rightPriceScale:{borderColor:'#2A2E39'},
    timeScale:{borderColor:'#2A2E39',timeVisible:true,secondsVisible:false,rightOffset:1,barSpacing:7},
    localization:{locale:'th-TH'},
  };
  // ── pane ราคาหลัก (ซ่อนแกนเวลา — แกนเวลาจะอยู่ที่แถบ ADX ล่างสุด) ──
  const el=document.getElementById('candleChart'); if(!el) return;
  lwChart=LightweightCharts.createChart(el,{...baseOpts,width:el.clientWidth||300,height:el.clientHeight||320,timeScale:{...baseOpts.timeScale,visible:false}});
  lwCandle=lwChart.addCandlestickSeries({
    upColor:'#26A69A',downColor:'#EF5350',borderVisible:false,
    wickUpColor:'#26A69A',wickDownColor:'#EF5350',
    priceFormat:{type:'custom',formatter:p=>p},
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
  // ── pane Volume — instance แยก (ไม่ทับราคา 100%) ──
  try{
    const vEl=document.getElementById('volChart');
    if(vEl){
      lwVolC=LightweightCharts.createChart(vEl,{...baseOpts,width:vEl.clientWidth||300,height:vEl.clientHeight||80,timeScale:{...baseOpts.timeScale,visible:false}});
      lwVol=lwVolC.addHistogramSeries({priceFormat:{type:'volume'}});
    }
  }catch(e){ console.error('volume pane fail',e); }
  // ── pane RSI — instance แยก มีเส้น 70/30 ของตัวเอง ──
  try{
    const rEl=document.getElementById('rsiChart');
    if(rEl){
      lwRsiC=LightweightCharts.createChart(rEl,{...baseOpts,width:rEl.clientWidth||300,height:rEl.clientHeight||96,timeScale:{...baseOpts.timeScale,visible:false}});
      lwRsi=lwRsiC.addLineSeries({color:'#9C6FE0',lineWidth:1,priceLineVisible:false,lastValueVisible:true,crosshairMarkerVisible:false,priceFormat:{type:'custom',formatter:v=>v==null?'–':v.toFixed(1)}});
      lwRsi.createPriceLine({price:70,color:'rgba(120,123,134,.45)',lineStyle:LightweightCharts.LineStyle.Dotted,title:'70'});
      lwRsi.createPriceLine({price:30,color:'rgba(120,123,134,.45)',lineStyle:LightweightCharts.LineStyle.Dotted,title:'30'});
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
      lwAdx.createPriceLine({price:20,color:'rgba(120,123,134,.5)',lineStyle:LightweightCharts.LineStyle.Dotted,title:'20'});
    }
  }catch(e){ console.error('adx pane fail',e); }
  _lwSyncPanes();   // pan/zoom ของทุกแถบขยับตามกัน
  _lwOHLClegend();
}

// ── sync pan/zoom ข้ามทุกแถบ (ตามแพทเทิร์นใน multi-pane-chart-demo.html) ──
function _lwSyncPanes(){
  _lwCharts=[lwChart,lwVolC,lwRsiC,lwAdxC].filter(Boolean);
  let syncing=false;
  _lwCharts.forEach(c=>{
    c.timeScale().subscribeVisibleLogicalRangeChange(range=>{
      if(syncing||!range) return;
      syncing=true;
      _lwCharts.forEach(o=>{ if(o!==c) o.timeScale().setVisibleLogicalRange(range); });
      syncing=false;
    });
  });
}

function refreshLWResize(){
  const map={'candleChart':lwChart,'volChart':lwVolC,'rsiChart':lwRsiC,'adxChart':lwAdxC};
  for(const id in map){
    const el=document.getElementById(id); const c=map[id];
    if(c&&el&&el.clientWidth>0) c.applyOptions({width:el.clientWidth,height:el.clientHeight||460});
  }
}


export { _candleTime, initLWChart, lwAdx, lwBbL, lwBbM, lwBbU, lwCandle, lwChart, lwEma100, lwEma200, lwEma50, lwNdi, lwPdi, lwRsi, lwSma5, lwVol, refreshLWResize };
