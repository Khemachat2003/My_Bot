// Probability Gauge M1/M5 — /api/ml/latest
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1908–1939, 2761–2769 แบบ move-only

import { fetchJSON } from '../../shared/api/client.js';

/* ═══════ SVG SEMICIRCLE GAUGE (C-8 premium: gradient arc + tick เกต + เลย์เอาต์ยืดหยุ่น) ═══════ */
function arcPath(cx,cy,r,a0,a1){
  const x0=cx+r*Math.cos(a0),y0=cy+r*Math.sin(a0);
  const x1=cx+r*Math.cos(a1),y1=cy+r*Math.sin(a1);
  const large=Math.abs(a1-a0)>Math.PI?1:0;
  return `M${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1}`;
}
// tick สั้นตั้งฉากรัศมี ณ มุม a — บอกตำแหน่งเกตบนเส้น arc
function tickLine(cx,cy,r,a){
  const x0=cx+(r-11)*Math.cos(a),y0=cy+(r-11)*Math.sin(a);
  const x1=cx+(r+11)*Math.cos(a),y1=cy+(r+11)*Math.sin(a);
  return `<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" stroke="#E8A33D" stroke-width="3" stroke-linecap="round"/>`;
}
function gaugeSVG(g){
  if(!g) return `<div class="gauge"><div class="gempty">รอข้อมูล</div></div>`;
  const up=g.prob_up*100, dn=g.prob_down*100;
  const cx=110, cy=72, r=58, w=13;
  const a0=Math.PI, aEnd=2*Math.PI;
  const upEnd=a0+(aEnd-a0)*Math.min(up,100)/100;
  const sigClass=g.signal==='CALL'?'CALL':(g.signal==='PUT'?'PUT':'NEUTRAL');
  // design_system C-3: เส้น gauge = --accent เสมอ (track = --dim), ทิศทางแยกเป็น badge ▲/▼ คู่สี
  const sigText=g.signal==='CALL'?'▲ CALL':(g.signal==='PUT'?'▼ PUT':'○ NEUTRAL');
  const thRaw=(g.env_threshold!=null?g.env_threshold:g.threshold_used);
  const thTick=(thRaw!=null)?tickLine(cx,cy,r,a0+(aEnd-a0)*Math.min(thRaw,1)):''; // ตำแหน่งเกตบน arc
  const tf=g.timeframe||'–';
  const gradId=`gArc-${tf}`;
  const center=g.signal==='NEUTRAL'?'NEUTRAL':(g.confidence*100).toFixed(0)+'%';
  return `<div class="gauge">
    <div class="g-row">
      <div class="g-info">
        <div class="g-tf">XAUUSD · ${tf}</div>
        <span class="gsig ${sigClass}">${sigText}</span>
        <div class="g-thresh">${thRaw!=null?('เกต ≥'+Math.round(thRaw*100)+'%'):''}</div>
      </div>
      <div class="gauge-svg">
        <svg viewBox="0 0 220 96" role="img" aria-label="${tf} win probability">
          <defs>
            <linearGradient id="${gradId}" x1="0" y1="1" x2="1" y2="0">
              <stop offset="0" stop-color="#2E5FB8"/><stop offset="1" stop-color="#7EB2FF"/>
            </linearGradient>
          </defs>
          <path d="${arcPath(cx,cy,r,a0,aEnd)}" stroke="#4C5566" stroke-width="${w}" fill="none" stroke-linecap="round"/>
          <path d="${arcPath(cx,cy,r,a0,upEnd)}" stroke="url(#${gradId})" stroke-width="${w}" fill="none" stroke-linecap="round"/>
          ${thTick}
          <text x="110" y="84" text-anchor="middle" font-size="19" font-weight="800" font-family="IBM Plex Mono,monospace" fill="#EDEFF3">${center}</text>
        </svg>
      </div>
    </div>
    <div class="gmeta">
      <span style="color:var(--bull);">▲ CALL ${up.toFixed(1)}%</span>
      <span style="color:var(--bear);">▼ PUT ${dn.toFixed(1)}%</span>
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
