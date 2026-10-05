// กราฟ Equity Curve เต็มในแท็บ Journal — Phase C-5 (design_system 5.1): mirror รูปแบบ C-3 ทุกค่า
// เส้นเดียวสี accent + baseline series (fill เหนือฐาน bull / ใต้ฐาน bear, สร้าง series ใหม่เมื่อฐานเปลี่ยน)
// — ตัด createPriceLine เส้นฐานเดิม 2 เส้น (baseline series วาดเส้นฐานเอง) — ไม่แตะ logic ข้อมูล (_buildEqData)

import { _buildEqData } from '../../shared/lib/equityData.js';
import { pnlText } from '../../shared/lib/pnlText.js';

const ACCENT='#4C8DFF', DIM='#4C5566';
const BULL_FILL1='rgba(22,199,132,0.22)', BULL_FILL2='rgba(22,199,132,0.03)';
const BEAR_FILL1='rgba(240,70,92,0.03)',  BEAR_FILL2='rgba(240,70,92,0.22)';

let lwEqFullChart=null, lwEqFullSeries=null, lwEqFullSeries2=null;
let lwEqFullBase=null, lwEqFullBase2=null; // base ปัจจุบันของแต่ละ series (เปลี่ยน → สร้างใหม่)
function drawEquityFull(payload){
  const el=document.getElementById('equityFullChart'); if(!el) return;
  const b=_buildEqData(payload&&payload.opt, payload&&payload.cfd);
  const cur=(payload&&payload.opt&&payload.opt.cur)||'THB';
  const fmt=p=>Number(p).toLocaleString('th-TH',{maximumFractionDigits:0});
  const emptyEl=document.getElementById('eqEmptyFull');
  const statsEl=document.getElementById('eqStatsFull');
  const hasData=b.optN+b.cfdN>0;
  if(emptyEl) emptyEl.style.display=hasData?'none':'block';
  if(!window.LightweightCharts) return;
  if(!lwEqFullChart){
    lwEqFullChart=LightweightCharts.createChart(el,{
      height:el.clientHeight||260, width:el.clientWidth||300,
      layout:{background:{color:'transparent'},textColor:'#838B9C',fontFamily:'IBM Plex Mono, monospace'},
      grid:{vertLines:{color:'#1A1D27'},horzLines:{color:'#1A1D27'}},
      rightPriceScale:{borderColor:'#232732'},
      timeScale:{borderColor:'#232732',rightOffset:2},
    });
    window.addEventListener('resize',()=>{ if(lwEqFullChart&&el.clientWidth>0) lwEqFullChart.applyOptions({width:el.clientWidth}); });
  }
  // สร้าง baseline series ใหม่เมื่อยังไม่มี หรือ base (ทุนเริ่มต้น) เปลี่ยน — baseline series วาดเส้นฐานเอง
  const mkSeries=(existing,curBase,prevBase,priceFmt)=>{
    if(existing&&prevBase===(curBase||0)) return existing;
    if(existing) lwEqFullChart.removeSeries(existing);
    return lwEqFullChart.addBaselineSeries({
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
    lwEqFullSeries=mkSeries(lwEqFullSeries,b.cfdBase,lwEqFullBase,{type:'custom',formatter:p=>'$'+fmt(p)});
    lwEqFullBase=b.cfdBase||0;
  }
  if(b.optN){
    lwEqFullSeries2=mkSeries(lwEqFullSeries2,b.optCapitalBase,lwEqFullBase2,{type:'custom',formatter:p=>fmt(p)+' '+cur});
    lwEqFullBase2=b.optCapitalBase||0;
  }
  if(lwEqFullSeries) lwEqFullSeries.setData(b.cfdPts);
  if(lwEqFullSeries2) lwEqFullSeries2.setData(b.optPts);
  lwEqFullChart.applyOptions({width:el.clientWidth||300,height:el.clientHeight||260});
  if(hasData) lwEqFullChart.timeScale().fitContent();
  if(statsEl){
    // chips: P&L คู่เครื่องหมาย + ศูนย์ไม่ติด eq-up (5.3)
    const chipPnl=(p)=>p>0
      ?`<span class="eq-up">(${pnlText(p,{digits:0})})</span>`
      :(p<0?`<span class="eq-dn">(${pnlText(p,{digits:0})})</span>`:`<span>(${pnlText(p,{digits:0})})</span>`);
    const chips=[];
    if(b.cfdN) chips.push(`CFD <b>$${fmt((b.cfdBase||0)+b.cfdPnl)}</b> ${chipPnl(b.cfdPnl)} · ${b.cfdN} เทรด`);
    if(b.optN) chips.push(`Option <b>${fmt((b.optCapitalBase||0)+b.optPnl)} ${cur}</b> ${chipPnl(b.optPnl)} · ${b.optN} เทรด`);
    if(!chips.length) chips.push('รอข้อมูลเทรดที่จบแล้ว');
    statsEl.innerHTML=chips.join('<span style="color:var(--border)"> | </span>');
  }
}


export { drawEquityFull };
