// Probability Gauge M1/M5 — /api/ml/latest
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1908–1939, 2761–2769 แบบ move-only

import { fetchJSON } from '../../shared/api/client.js';

/* ═══════ RING GAUGE (C-8 premium v3: วงแหวนเต็ม + glow + sweep animation + จุดเกต) ═══════ */
const R_CX=60, R_CY=60, R_R=52, R_C=2*Math.PI*R_R; // เส้นรอบวง ≈ 326.73
function ringGauge(g){
  if(!g) return `<div class="gauge"><div class="gempty">รอข้อมูล</div></div>`;
  const up=Math.min(g.prob_up*100,100);
  const sigClass=g.signal==='CALL'?'CALL':(g.signal==='PUT'?'PUT':'NEUTRAL');
  const sigText=g.signal==='CALL'?'▲ CALL':(g.signal==='PUT'?'▼ PUT':'○ NEUTRAL');
  const thRaw=(g.env_threshold!=null?g.env_threshold:g.threshold_used);
  // จุดเกตบนวง: เริ่ม 12 นาฬิกา (rotate -90) ตามเข็ม
  let thDot='';
  if(thRaw!=null){
    const a=(Math.min(thRaw,1)*360-90)*Math.PI/180;
    thDot=`<circle cx="${(R_CX+R_R*Math.cos(a)).toFixed(2)}" cy="${(R_CY+R_R*Math.sin(a)).toFixed(2)}" r="4.5" fill="#E8A33D" stroke="#0A0C10" stroke-width="2"/>`;
  }
  const off=(R_C*(1-up/100)).toFixed(2);
  const gradId=`gRing-${g.timeframe||'x'}`;
  const val=g.confidence*100;
  return `<div class="gauge">
    <div class="g-top">
      <span class="g-tf">XAUUSD · ${g.timeframe||'–'}</span>
      <span class="gsig ${sigClass}">${sigText}</span>
    </div>
    <div class="g-ring">
      <svg viewBox="0 0 120 120" role="img" aria-label="${g.timeframe||''} ring">
        <defs>
          <linearGradient id="${gradId}" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#2E5FB8"/><stop offset="1" stop-color="#7EB2FF"/>
          </linearGradient>
        </defs>
        <circle cx="${R_CX}" cy="${R_CY}" r="${R_R}" stroke="#232732" stroke-width="9" fill="none"/>
        <circle class="g-arc" cx="${R_CX}" cy="${R_CY}" r="${R_R}" stroke="url(#${gradId})" stroke-width="10" fill="none"
          stroke-linecap="round" stroke-dasharray="${R_C.toFixed(2)}" stroke-dashoffset="${off}"
          transform="rotate(-90 ${R_CX} ${R_CY})"/>
        ${thDot}
      </svg>
      <div class="g-val">${val.toFixed(0)}<small>%</small></div>
    </div>
    <div class="g-chips">
      <span class="g-chip up">▲ ${up.toFixed(1)}%</span>
      <span class="g-chip th">${thRaw!=null?('เกต ≥'+Math.round(thRaw*100)+'%'):'–'}</span>
      <span class="g-chip dn">▼ ${dn_(g)}%</span>
    </div>
  </div>`;
}
function dn_(g){ return Math.min(g.prob_down*100,100).toFixed(1); }

async function refreshGauges(){
  try{
    const latest=await fetchJSON('/api/ml/latest');
    const panel=document.getElementById('gaugePanel');
    const m1=latest['M1'], m5=latest['M5'];
    panel.innerHTML=ringGauge(m1?{...m1,timeframe:'M1'}:null)+ringGauge(m5?{...m5,timeframe:'M5'}:null);
  }catch(e){}
}


export { refreshGauges };
