// การ์ด/แถว 11-Checklist (render HTML)
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2953–3041 แบบ move-only

import { dirClass } from '../../shared/lib/formatSignal.js';

const SETUP_STEPS=[
  ['c1_fractal_sr','1. Fractal 15 S/R'],
  ['c2_bb_break','2. BB Break'],
  ['c3_rsi_ob_os','3. RSI OVB/OVS'],
  ['c4_rsi_div','4. RSI Divergence'],
  ['c5_adx','5. ADX > 20'],
  ['c6_pa','6. PA Confirmation'],
  ['c7_fractal_trend','7. Fractal Trend'],
  ['c8_grip','8. Grip'],
  ['c9_bb_width','9. BB Width'],
  ['c10_mtf','10. MTF Trend'],
];
const BIAS_TXT={
  'BULLISH_TREND':'▲ CALL',
  'BEARISH_TREND':'▼ PUT',
};
const TIER_ACTION={
  'FIRE':'🔥 Ready',
  'WATCH':'⏳ Waiting',
  'NONE':'–',
};
const IMPORTANCE_TXT={
  1:'🚨 EMA200 Touch',
  2:'⏳ EMA100 Cross',
};
const _symShort=s=>(s||'').replace(/^frx/,'').replace(/_/g,'');
function renderSetupCard(s){
  if(!s) return `<div class="guide-card NONE"><div class="guide-head"><span class="guide-tf">Setup</span></div><div class="guide-action NONE">ยังไม่มีข้อมูล</div></div>`;
  const max=(s.max_score||s.total||10);
  const details=s.details||{};
  const condLog=s.conditions_log||{};
  const source=Object.keys(condLog).length>0?condLog:details;
  const known=SETUP_STEPS.map(x=>x[0]);
  const steps=[];
  SETUP_STEPS.forEach(([key,label])=>{
    const d=source[key]||details[key]; if(!d) return;
    const frac=d.frac!=null?d.frac:(d.ok?1:(d.pass!=null?(d.pass?1:0):0));
    const cls=frac>=0.999?'pass':(frac>0?'part':'fail');
    const ico=frac>=0.999?'✓':(frac>0?'◐':'✕');
    steps.push(`<li><span class="guide-ico ${cls}">${ico}</span><span class="gname">${label}</span><span class="gnote">${d.note||''}</span></li>`);
  });
  const tier=s.tier||'NONE';
  const bias=s.bias||'';
  const biasTxt=BIAS_TXT[bias]||'NEUTRAL';
  const imp=s.importance||0;
  const condPassed=s.conditions_passed||0;
  const condTotal=s.conditions_total||10;
  const sym=s.symbol||'';
  const scorePct=Math.round((condPassed/Math.max(condTotal,1))*100);
  const scoreCls=tier==='FIRE'?'ok':(tier==='WATCH'?'wait':'none');
  return `<div class="guide-card ${tier}">
    <div class="guide-head">
      <span class="guide-tf">${_symShort(sym)||'XAUUSD'} · ${s.timeframe||'M5'}</span>
      <span class="guide-score ${scoreCls}">${condPassed}/${condTotal}</span>
    </div>
    <div class="guide-action ${tier}">${TIER_ACTION[tier]||'–'} <span class="${dirClass(s.direction)}">${biasTxt}</span>${imp?` · ${IMPORTANCE_TXT[imp]}`:''}</div>
    <ul class="guide-steps">${steps.join('')}</ul>
    ${s.entry_trigger_note?`<div class="guide-note ${tier==='FIRE'?'ready':'wait'}">${s.entry_trigger_note}</div>`:''}
  </div>`;
}
function renderSetupCompact(s){
  if(!s) return '';
  const tier=s.tier||'NONE';
  const bias=s.bias||'';
  const imp=s.importance||0;
  const condPassed=s.conditions_passed||0;
  const condTotal=s.conditions_total||10;
  const sym=s.symbol||'';
  const biasTxt=BIAS_TXT[bias]||'–';
  const tierCls=tier==='FIRE'?'ok':(tier==='WATCH'?'wait':'none');
  return `<div class="setup-row" data-sym="${sym}" data-toggle-self="expanded">
    <div class="setup-row-head">
      <span class="setup-sym">${_symShort(sym)}</span>
      <span class="setup-tier ${tierCls}">${tier}</span>
      <span class="setup-dir ${dirClass(s.direction)}">${biasTxt}</span>
      <span class="setup-score">${condPassed}/${condTotal}</span>
    </div>
    <div class="setup-row-detail">${renderSetupCard(s)}</div>
  </div>`;
}

function _getExpandedSetup(){
  const s=new Set();
  document.querySelectorAll('.setup-row.expanded').forEach(r=>{ if(r.dataset.sym) s.add(r.dataset.sym); });
  return s;
}
function _restoreExpandedSetup(container,expanded){
  container.querySelectorAll('.setup-row').forEach(r=>{ if(expanded.has(r.dataset.sym)) r.classList.add('expanded'); });
}

export { TIER_ACTION, _getExpandedSetup, _restoreExpandedSetup, renderSetupCompact };
