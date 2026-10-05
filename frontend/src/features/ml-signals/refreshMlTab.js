// แท็บ ML — /api/ml/stats, /api/ml/stats/by_timeframe, /api/ml/signals
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2797–2845 แบบ move-only

import { feedRow } from './feedRow.js';
import { moneyReport } from '../journal/index.js';
import { fetchJSON } from '../../shared/api/client.js';
import { fmtMargin } from '../../shared/lib/formatSignal.js';
import { fmtTime } from '../../shared/lib/formatTime.js';
import { ensureMarkers } from '../../shared/lib/markersCache.js';
import { renderStat } from '../../shared/ui/domText.js';
import { cfdCells, dirBadge } from '../../shared/lib/signalRows.js';

async function refreshMlTab(){
  try{
    const s=await fetchJSON('/api/ml/stats');
    renderStat(document.getElementById('mlWr'),s.n_resolved?s.winrate+'%':'–',s.n_resolved?'cyan':'muted');
    document.getElementById('mlWrSub').textContent=s.n_resolved?`[${s.ci_low}% – ${s.ci_high}%] (${s.wins}/${s.n_resolved})`:'';
    document.getElementById('mlN').textContent=`${s.n_resolved} / ${s.n_pending}`;
    document.getElementById('mlNsub').textContent=`ชนะ ${s.wins} / แพ้ ${s.losses}`;
    document.getElementById('mlBe').textContent=s.breakeven+'%';
    document.getElementById('mlMargin').textContent=s.n_resolved?fmtMargin(s.margin):'–';
    document.getElementById('mlCi').textContent=s.n_resolved?`[${s.ci_low}%, ${s.ci_high}%]`:'–';
    const byTf=await fetchJSON('/api/ml/stats/by_timeframe');
    const t1=byTf['M1']||{}, t5=byTf['M5']||{};
    const setWin=(id,v)=>{const el=document.getElementById(id);
      if(v&&v.n_resolved){el.textContent=v.winrate+'%';} else {el.textContent='–';}};
    setWin('mlWrM1',t1); setWin('mlWrM5',t5);
    const setN=(id,v)=>{const el=document.getElementById(id);if(el) el.textContent=v&&v.n_resolved?v.n_resolved:'–';};
    setN('mlM1N',t1); setN('mlM5N',t5);
    const cur=moneyReport?.settings?.currency||'THB';
    const setPnl=(id,v)=>{const el=document.getElementById(id);
      if(!el)return;
      if(v&&v.n_resolved&&v.pnl_money!=null){el.textContent=(v.pnl_money>0?'+':'')+Number(v.pnl_money).toLocaleString('th-TH',{maximumFractionDigits:0})+' '+cur;}
      else el.textContent='–';};
    setPnl('mlM1Pnl',t1); setPnl('mlM5Pnl',t5);
  }catch(e){}
  try{
    // C-4: ดึง markers คู่ไปกับ rows (แคชสด → no-op) — SL/TP/R:R อ่านจาก markers เดียวกับกราฟ
    const [rows,markers]=await Promise.all([
      fetchJSON('/api/ml/signals?limit=100'),
      ensureMarkers(),
    ]);
    const body=document.querySelector('#mlFullTable tbody');
    const empty=document.getElementById('mlEmpty');
    if(!rows.length){body.innerHTML='';empty.style.display='block';return;}
    empty.style.display='none';
    body.innerHTML=rows.map(r=>`<tr>
      <td>${fmtTime(r.signal_time)}</td>
      <td><b>${r.timeframe||'M1'}</b></td>
      <td>${dirBadge(r.direction)}</td>
      <td class="mono">${r.entry_price!=null?r.entry_price.toFixed(2):'–'}</td>
      ${cfdCells('ML',r.id,markers,2)}
      <td class="mono">${r.exit_price!=null?r.exit_price.toFixed(2):'–'}</td>
      <td class="mono">${r.confidence!=null?(r.confidence*100).toFixed(1)+'%':'–'}</td>
      <td class="mono">${r.threshold_used!=null?(r.threshold_used*100).toFixed(0)+'%':'–'}</td>
      <td class="mono">${r.horizon_min}m</td>
      <td style="font-size:10px;color:var(--muted)">${r.model_version||'–'}${r.confidence!=null&&r.confidence>0.7?' <span class="hi-badge">HIGH</span>':''}</td>
      <td><span class="pill ${r.result}">${r.result}</span></td>
    </tr>`).join('');
  }catch(e){}
  try{
    const rows=await fetchJSON('/api/ml/signals?limit=8');
    document.getElementById('mlRecentFeed').innerHTML=rows.length?rows.map(feedRow).join(''):'<div class="empty">ยังไม่มีสัญญาณ</div>';
  }catch(e){}
}


export { refreshMlTab };
