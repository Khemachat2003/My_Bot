// แถวสัญญาณในฟีด "สัญญาณล่าสุด"
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2786–2796 แบบ move-only

import { fmtHM } from '../../shared/lib/formatTime.js';

function feedRow(r){
  const hi=(r.confidence!=null&&r.confidence>0.7)?' <span class="hi-badge">HIGH</span>':'';
  return `<div class="feed-row">
    <span class="fdir ${r.direction||''}">${r.direction||'–'}</span>
    <span class="ftime">${fmtHM(r.signal_time)}</span>
    <span class="fprice">${r.entry_price!=null?r.entry_price.toFixed(2):'–'}</span>
    <span class="fconf">${r.confidence!=null?(r.confidence*100).toFixed(1)+'%':'–'}${hi}</span>
    <span class="pill ${r.result}">${r.result}</span>
  </div>`;
}


export { feedRow };
