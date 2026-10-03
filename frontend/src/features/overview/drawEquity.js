// กราฟ Equity Curve ในแท็บภาพรวม
// Phase C-3 (design_system 5.1): เส้นเดียวสี --accent + fill เหนือฐาน --bull-dim / ใต้ฐาน --bear-dim
// (baseline = ทุนเริ่มต้น) — ไม่เปลี่ยนสีเส้นตามช่วงขึ้น/ลง

import { _buildEqData } from '../../shared/lib/equityData.js';

const ACCENT='#4C8DFF', DIM='#4C5566';
const BULL_FILL1='rgba(22,199,132,0.22)', BULL_FILL2='rgba(22,199,132,0.03)';
const BEAR_FILL1='rgba(240,70,92,0.03)',  BEAR_FILL2='rgba(240,70,92,0.22)';

let lwEqChart=null, lwEqSeries=null, lwEqSeries2=null;
let lwEqBase=null, lwEqBase2=null; // base ปัจจุบันของแต่ละ series (เปลี่ยน → สร้างใหม่)
function drawEquity(payload){
  const el=document.getElementById('equityChart'); if(!el) return;
  const b=_buildEqData(payload&&payload.opt, payload&&payload.cfd);
  const cur=(payload&&payload.opt&&payload.opt.cur)||'THB';
  const statsEl=document.getElementById('eqStatsOv');
  const emptyEl=document.getElementById('eqEmptyOv');
  if(!window.LightweightCharts) return;
  if(!lwEqChart){
    lwEqChart=LightweightCharts.createChart(el,{
      height:el.clientHeight||260, width:el.clientWidth||300,
      layout:{background:{color:'transparent'},textColor:'#838B9C',fontFamily:'IBM Plex Mono, monospace'},
      grid:{vertLines:{color:'#1A1D27'},horzLines:{color:'#1A1D27'}},
      rightPriceScale:{borderColor:'#232732'},
      timeScale:{borderColor:'#232732',rightOffset:2},
    });
    window.addEventListener('resize',()=>{ if(lwEqChart&&el.clientWidth>0) lwEqChart.applyOptions({width:el.clientWidth}); });
  }
  const fmt=p=>Number(p).toLocaleString('th-TH',{maximumFractionDigits:0});
  // สร้าง baseline series ใหม่เมื่อยังไม่มี หรือ base (ทุนเริ่มต้น) เปลี่ยน — baseline series วาดเส้นฐานเอง
  const mkSeries=(existing,curBase,prevBase,priceFmt)=>{
    if(existing&&prevBase===(curBase||0)) return existing;
    if(existing) lwEqChart.removeSeries(existing);
    return lwEqChart.addBaselineSeries({
      baseValue:{type:'price',price:curBase||0},
      lineColor:ACCENT, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM,
      topFillColor1:BULL_FILL1, topFillColor2:BULL_FILL2,
      bottomLineColor:DIM, bottomLineColor1:DIM,
      bottomFillColor1:BEAR_FILL1, bottomFillColor2:BEAR_FILL2,
      priceLineVisible:false, lastValueVisible:false, priceFormat:priceFmt,
    });
  };
  if(b.cfdN){
    lwEqSeries=mkSeries(lwEqSeries,b.cfdBase,lwEqBase,{type:'custom',formatter:p=>'$'+fmt(p)});
    lwEqBase=b.cfdBase||0;
  }
  if(b.optN){
    lwEqSeries2=mkSeries(lwEqSeries2,b.optCapitalBase,lwEqBase2,{type:'custom',formatter:p=>fmt(p)+' '+cur});
    lwEqBase2=b.optCapitalBase||0;
  }
  if(lwEqSeries) lwEqSeries.setData(b.cfdPts);
  if(lwEqSeries2) lwEqSeries2.setData(b.optPts);
  lwEqChart.applyOptions({width:el.clientWidth||300,height:el.clientHeight||260});
  if(b.optN+b.cfdN>0) lwEqChart.timeScale().fitContent();
  if(emptyEl) emptyEl.style.display=(b.optN+b.cfdN)>0?'none':'block';
  if(statsEl){
    const chips=[];
    if(b.cfdN) chips.push(`CFD <b>$${fmt((b.cfdBase||0)+b.cfdPnl)}</b> <span class="eq-${b.cfdPnl>=0?'up':'dn'}">(${b.cfdPnl>=0?'+':''}${fmt(b.cfdPnl)})</span> · ${b.cfdN} เทรด`);
    if(b.optN) chips.push(`Option <b>${fmt(b.optCapitalBase+b.optPnl)} ${cur}</b> <span class="eq-${b.optPnl>=0?'up':'dn'}">(${b.optPnl>=0?'+':''}${fmt(b.optPnl)})</span> · ${b.optN} เทรด`);
    if(!chips.length) chips.push('รอข้อมูลเทรดที่จบแล้ว');
    statsEl.innerHTML=chips.join('<span style="color:var(--border)"> | </span>');
  }
}


export { drawEquity };
