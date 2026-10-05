// แท็บ Rule-Based — /api/stats, /api/stats/by_timeframe, /api/signals
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2846–2896, 3249 แบบ move-only

import { moneyReport } from '../journal/index.js';
import { TIER_ACTION } from './setupCards.js';
import { fetchJSON } from '../../shared/api/client.js';
import { fmtMargin } from '../../shared/lib/formatSignal.js';
import { fmtTime } from '../../shared/lib/formatTime.js';
import { ensureMarkers } from '../../shared/lib/markersCache.js';
import { renderStat } from '../../shared/ui/domText.js';
import { cfdCells, dirBadge } from '../../shared/lib/signalRows.js';
import { refreshTickTouchResearch } from './tickTouchResearch.js';

async function refreshSetupTab(){
  try{
    const s=await fetchJSON('/api/stats');
    renderStat(document.getElementById('setWr'),s.n_resolved?s.winrate+'%':'–',s.n_resolved?'blue':'muted');
    document.getElementById('setWrSub').textContent=s.n_resolved?`[${s.ci_low}% – ${s.ci_high}%] (${s.wins}/${s.n_resolved})`:'';
    document.getElementById('setN').textContent=`${s.n_resolved} / ${s.n_pending}`;
    document.getElementById('setNsub').textContent=`ชนะ ${s.wins} / แพ้ ${s.losses}`;
    document.getElementById('setBe').textContent=s.breakeven+'%';
    document.getElementById('setMargin').textContent=s.n_resolved?fmtMargin(s.margin):'–';
    document.getElementById('setCi').textContent=s.n_resolved?`[${s.ci_low}%, ${s.ci_high}%]`:'–';
    const byTf=await fetchJSON('/api/stats/by_timeframe');
    const t1=byTf['M1']||{}, t5=byTf['M5']||{};
    const setWin=(id,v)=>{const el=document.getElementById(id);
      if(v&&v.n_resolved){el.textContent=v.winrate+'%';} else {el.textContent='–';}};
    setWin('setWrM1',t1); setWin('setWrM5',t5);
    const setN=(id,v)=>{const el=document.getElementById(id);if(el) el.textContent=v&&v.n_resolved?v.n_resolved:'–';};
    setN('setM1N',t1); setN('setM5N',t5);
    const cur=moneyReport?.settings?.currency||'THB';
    const setPnl=(id,v)=>{const el=document.getElementById(id);
      if(!el)return;
      if(v&&v.n_resolved&&v.pnl_money!=null){el.textContent=(v.pnl_money>0?'+':'')+Number(v.pnl_money).toLocaleString('th-TH',{maximumFractionDigits:0})+' '+cur;}
      else el.textContent='–';};
    setPnl('setM1Pnl',t1); setPnl('setM5Pnl',t5);
  }catch(e){}
  try{
    const sym=document.getElementById('setupSymFilter').value;
    // C-4: ดึง markers คู่ไปกับ rows (แคชสด → no-op) — SL/TP/R:R อ่านจาก markers เดียวกับกราฟ
    const [rows,markers]=await Promise.all([
      fetchJSON('/api/signals?limit=100'+(sym?'&symbol='+encodeURIComponent(sym):'')),
      ensureMarkers(),
    ]);
    const body=document.querySelector('#setupTable tbody');
    const empty=document.getElementById('setEmpty');
    if(!rows.length){body.innerHTML='';empty.style.display='block';return;}
    empty.style.display='none';
    body.innerHTML=rows.map(r=>{
      const impLabel=r.importance===1?'IMP1':r.importance===2?'IMP2':'';
      const impColor=r.importance===1?'var(--red)':r.importance===2?'var(--yellow)':'var(--muted)';
      return `<tr>
      <td>${fmtTime(r.signal_time)}</td>
      <td><b>${(r.symbol||'frxXAUUSD').replace('frx','')}</b></td>
      <td><b>${r.timeframe||'M1'}</b></td>
      <td style="color:${impColor};font-weight:700;font-size:11px;">${impLabel||'–'}</td>
      <td>${dirBadge(r.direction)}</td>
      <td class="mono">${r.entry_price!=null?r.entry_price.toFixed(5):'–'}</td>
      ${cfdCells('SETUP',r.id,markers,5)}
      <td class="mono">${r.exit_price!=null?r.exit_price.toFixed(5):'–'}</td>
      <td class="mono">${r.score!=null?r.score.toFixed(1)+'/'+(r.total||'–'):'–'}</td>
      <td><span class="tier ${r.tier||'NONE'}">${TIER_ACTION[r.tier]?r.tier:'–'}</span></td>
      <td class="mono">${r.details?Object.values(r.details).filter(d=>d.frac!=null?d.frac>=0.999:d.ok).length+'/11':'–'}</td>
      <td><span class="pill ${r.result}">${r.result}</span></td>
    </tr>`;}).join('');
  }catch(e){}
  await refreshTickTouchResearch();
}

document.getElementById('setupSymFilter')?.addEventListener('change',()=>refreshSetupTab());

export { refreshSetupTab };
