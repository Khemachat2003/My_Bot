// กราฟ Equity Curve เต็มในแท็บ Journal
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3191–3242 แบบ move-only

import { _buildEqData } from '../../shared/lib/equityData.js';

let lwEqFullChart=null, lwEqFullSeries=null, lwEqFullSeries2=null, lwEqFullBase=null, lwEqFullBase2=null;
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
      layout:{background:{color:'transparent'},textColor:'#787B86',fontFamily:'IBM Plex Mono, monospace'},
      grid:{vertLines:{color:'#1E222D'},horzLines:{color:'#1E222D'}},
      rightPriceScale:{borderColor:'#2A2E39'},
      timeScale:{borderColor:'#2A2E39',rightOffset:2},
    });
    window.addEventListener('resize',()=>{ if(lwEqFullChart&&el.clientWidth>0) lwEqFullChart.applyOptions({width:el.clientWidth}); });
  }
  if(b.cfdN && !lwEqFullSeries){
    lwEqFullSeries=lwEqFullChart.addAreaSeries({
      lineColor:'#26A69A', topColor:'rgba(38,166,154,0.28)', bottomColor:'rgba(38,166,154,0.02)',
      lineWidth:2, priceLineVisible:false, lastValueVisible:false,
      priceFormat:{type:'custom',formatter:p=>'$'+fmt(p)},
    });
    lwEqFullBase=lwEqFullSeries.createPriceLine({price:b.cfdBase||0,color:'#787B86',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,title:'CFD ทุน'});
  }
  if(b.optN && !lwEqFullSeries2){
    lwEqFullSeries2=lwEqFullChart.addAreaSeries({
      lineColor:'#2962FF', topColor:'rgba(41,98,255,0.20)', bottomColor:'rgba(41,98,255,0.02)',
      lineWidth:2, priceLineVisible:false, lastValueVisible:false,
      priceFormat:{type:'custom',formatter:p=>fmt(p)+' '+cur},
    });
    lwEqFullBase2=lwEqFullSeries2.createPriceLine({price:b.optCapitalBase||0,color:'#787B86',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,title:'Option ทุน'});
  }
  if(lwEqFullSeries) lwEqFullSeries.setData(b.cfdPts);
  if(lwEqFullSeries2) lwEqFullSeries2.setData(b.optPts);
  if(lwEqFullBase) lwEqFullBase.applyOptions({price:b.cfdBase||0});
  if(lwEqFullBase2) lwEqFullBase2.applyOptions({price:b.optCapitalBase||0});
  lwEqFullChart.applyOptions({width:el.clientWidth||300,height:el.clientHeight||260});
  if(hasData) lwEqFullChart.timeScale().fitContent();
  if(statsEl){
    const chips=[];
    if(b.cfdN) chips.push(`CFD <b>$${fmt((b.cfdBase||0)+b.cfdPnl)}</b> <span class="eq-${b.cfdPnl>=0?'up':'dn'}">(${b.cfdPnl>=0?'+':''}${fmt(b.cfdPnl)})</span> · ${b.cfdN} เทรด`);
    if(b.optN) chips.push(`Option <b>${fmt((b.optCapitalBase||0)+b.optPnl)} ${cur}</b> <span class="eq-${b.optPnl>=0?'up':'dn'}">(${b.optPnl>=0?'+':''}${fmt(b.optPnl)})</span> · ${b.optN} เทรด`);
    if(!chips.length) chips.push('รอข้อมูลเทรดที่จบแล้ว');
    statsEl.innerHTML=chips.join('<span style="color:var(--border)"> | </span>');
  }
}


export { drawEquityFull };
