// legend OHLC + ค่า indicator เหนือกราฟ
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2353, 2355–2388 แบบ move-only

import { _lwLastBar, _lwLastPrev } from './drawLwChart.js';
import { lwBbM, lwCandle, lwChart, lwEma50, lwSma5 } from './lwChartInit.js';

// ── LW legend bar: OHLC ของแท่งที่ crosshair ชี้ + ค่า indicator เทียบสีที่เปิดอยู่ ──
function _renderLWDefaultLegend(){
  const el=document.getElementById('lbValues'); if(!el) return;
  const b=_lwLastBar; if(!b){ el.innerHTML=''; return; }
  const pct=_lwLastPrev!=null?(b.close-_lwLastPrev)/_lwLastPrev*100:0;
  const cls=!isNaN(b.close)&&b.close>=b.open&&!isNaN(b.open)?'v-u':'v-d';
  el.innerHTML=`<span class="v-m">ราคา</span> <b class="${cls}">${b.close}</b> <span class="v-m">·</span> <span class="${cls}">${pct>=0?'+':''}${pct.toFixed(2)}%</span> <span class="v-m">·</span> <span class="v-m">${b.time?new Date(b.time*1000).toLocaleTimeString('th-TH'):''}</span>`+
    (window.__lastRsi!=null?` <span class="v-m">·</span> <span class="v-m" style="color:#9C6FE0;">RSI</span> <b>${Number(window.__lastRsi).toFixed(1)}</b>`:'')+
    (window.__lastAdx!=null?` <span class="v-m">·</span> <span class="v-m" style="color:#FF9800;">ADX</span> <b>${Number(window.__lastAdx).toFixed(1)}</b>`:'');
}
function _lwOHLClegend(){
  const el=document.getElementById('lbOhlc'); if(!el) return;
  if(!lwCandle) return;
  lwChart.subscribeCrosshairMove(param=>{
    if(!param||!param.time||!param.point||!param.seriesData){ _renderLWDefaultLegend(); return; }
    const d=param.seriesData.get(lwCandle);
    if(!d){ el.innerHTML='—'; _renderLWDefaultLegend(); return; }
    const up=d.close!=null&&d.open!=null&&d.close>=d.open;
    const cls=up?'up':'dn';
    el.innerHTML=`O <b class="${cls}">${d.open}</b> H <b class="${cls}">${d.high}</b> L <b class="${cls}">${d.low}</b> C <b class="${cls}">${d.close}</b>`;
    const vEl=document.getElementById('lbValues');
    if(vEl){
      const parts=[];
      const push=(s,series)=>{
        if(!series) return;
        const v=param.seriesData.get(series);
        if(v&&v.value!=null) parts.push(`<span class="v-m">${s}</span> <b>${v.value}</b>`);
      };
      push('EMA50',lwEma50); push('BB',lwBbM); push('SMA5',lwSma5);
      if(parts.length) vEl.innerHTML=parts.join('');
      else _renderLWDefaultLegend();
    }
  });
}


export { _lwOHLClegend, _renderLWDefaultLegend };
