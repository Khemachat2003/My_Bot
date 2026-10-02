// กราฟ Equity Curve ในแท็บภาพรวม
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2028–2078 แบบ move-only

import { _buildEqData } from '../../shared/lib/equityData.js';

let lwEqChart=null, lwEqSeries=null, lwEqSeries2=null, lwEqBaseLine=null, lwEqBaseLine2=null;
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
      layout:{background:{color:'transparent'},textColor:'#787B86',fontFamily:'IBM Plex Mono, monospace'},
      grid:{vertLines:{color:'#1E222D'},horzLines:{color:'#1E222D'}},
      rightPriceScale:{borderColor:'#2A2E39'},
      timeScale:{borderColor:'#2A2E39',rightOffset:2},
    });
    window.addEventListener('resize',()=>{ if(lwEqChart&&el.clientWidth>0) lwEqChart.applyOptions({width:el.clientWidth}); });
  }
  const fmt=p=>Number(p).toLocaleString('th-TH',{maximumFractionDigits:0});
  if(b.cfdN && !lwEqSeries){
    lwEqSeries=lwEqChart.addAreaSeries({
      lineColor:'#26A69A', topColor:'rgba(38,166,154,0.28)', bottomColor:'rgba(38,166,154,0.02)',
      lineWidth:2, priceLineVisible:false, lastValueVisible:false,
      priceFormat:{type:'custom',formatter:p=>'$'+fmt(p)},
    });
    lwEqBaseLine=lwEqSeries.createPriceLine({price:b.cfdBase||0,color:'#787B86',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,title:'CFD ทุน'});
  }
  if(b.optN && !lwEqSeries2){
    lwEqSeries2=lwEqChart.addAreaSeries({
      lineColor:'#2962FF', topColor:'rgba(41,98,255,0.20)', bottomColor:'rgba(41,98,255,0.02)',
      lineWidth:2, priceLineVisible:false, lastValueVisible:false,
      priceFormat:{type:'custom',formatter:p=>fmt(p)+' '+cur},
    });
    lwEqBaseLine2=lwEqSeries2.createPriceLine({price:b.optCapitalBase||0,color:'#787B86',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,title:'Option ทุน'});
  }
  if(lwEqSeries) lwEqSeries.setData(b.cfdPts);
  if(lwEqSeries2) lwEqSeries2.setData(b.optPts);
  if(lwEqBaseLine) lwEqBaseLine.applyOptions({price:b.cfdBase||0});
  if(lwEqBaseLine2) lwEqBaseLine2.applyOptions({price:b.optCapitalBase||0});
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
