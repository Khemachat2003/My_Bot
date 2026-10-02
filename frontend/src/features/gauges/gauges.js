// Probability Gauge M1/M5 — /api/ml/latest
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1908–1939, 2761–2769 แบบ move-only

import { fetchJSON } from '../../shared/api/client.js';

/* ═══════ SVG SEMICIRCLE GAUGE ═══════ */
function arcPath(cx,cy,r,a0,a1){
  const x0=cx+r*Math.cos(a0),y0=cy+r*Math.sin(a0);
  const x1=cx+r*Math.cos(a1),y1=cy+r*Math.sin(a1);
  const large=Math.abs(a1-a0)>Math.PI?1:0;
  return `M${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1}`;
}
function gaugeSVG(g){
  if(!g) return `<div class="gauge"><div class="ghead"><span class="gname">TF</span><span class="gsig NEUTRAL">–</span></div><div class="empty" style="padding:8px;">รอข้อมูล</div></div>`;
  const up=g.prob_up*100, dn=g.prob_down*100;
  const cx=110, cy=72, r=58, w=13;
  const a0=Math.PI, aEnd=2*Math.PI;
  const upEnd=a0+(aEnd-a0)*Math.min(up,100)/100;
  const sigClass=g.signal==='CALL'?'CALL':(g.signal==='PUT'?'PUT':'NEUTRAL');
  return `<div class="gauge">
    <div class="ghead"><span class="gname">XAUUSD · TF ${g.timeframe||'–'} — WIN PROBABILITY</span><span class="gsig ${sigClass}">${g.signal||'–'}</span></div>
    <div class="gauge-svg">
      <svg width="220" height="96" viewBox="0 0 220 96">
        <path d="${arcPath(cx,cy,r,a0,aEnd)}" stroke="#1C2029" stroke-width="${w}" fill="none" stroke-linecap="round"/>
        <path d="${arcPath(cx,cy,r,a0,upEnd)}" stroke="#26A69A" stroke-width="${w}" fill="none" stroke-linecap="round"/>
        <path d="${arcPath(cx,cy,r,upEnd,aEnd)}" stroke="#EF5350" stroke-width="${w}" fill="none" stroke-linecap="round"/>
        <text x="110" y="84" text-anchor="middle" font-size="20" font-weight="800" font-family="IBM Plex Mono,monospace" fill="#EDEFF3">${g.signal==='NEUTRAL'?'NEUTRAL':(g.confidence*100).toFixed(0)+'%'}</text>
      </svg>
    </div>
    <div class="gmeta">
      <span style="color:var(--green);">▲ CALL ${up.toFixed(1)}%</span>
      <span>Thresh ${(g.env_threshold!=null?g.env_threshold:g.threshold_used)*100|0}%</span>
      <span style="color:var(--red);">▼ PUT ${dn.toFixed(1)}%</span>
    </div>
  </div>`;
}

async function refreshGauges(){
  try{
    const latest=await fetchJSON('/api/ml/latest');
    const panel=document.getElementById('gaugePanel');
    const m1=latest['M1'], m5=latest['M5'];
    panel.innerHTML=gaugeSVG(m1?{...m1,timeframe:'M1'}:null)+gaugeSVG(m5?{...m5,timeframe:'M5'}:null);
  }catch(e){}
}


export { refreshGauges };
