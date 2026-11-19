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
    renderMlGuide(s);
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
    body.innerHTML=rows.map(r=>{
      // C-8 premium: Win Prob เป็นแถบmeter + model เป็น chip จาง
      const conf=r.confidence!=null?r.confidence*100:null;
      const confCol=conf==null?'muted':(conf>=70?'bull':(conf>=60?'warn':'muted'));
      const confCell=conf==null?'<span class="dl-muted">–</span>'
        :`<span class="mdl-meter"><span class="dl-track"><i style="width:${Math.min(conf,100)}%;background:var(--${confCol})"></i></span><b style="color:var(--${confCol})">${conf.toFixed(1)}%</b></span>`;
      return `<tr>
      <td class="mono mdl-dim">${fmtTime(r.signal_time)}</td>
      <td><span class="mdl-key">${r.timeframe||'M1'}</span></td>
      <td>${dirBadge(r.direction)}</td>
      <td class="mono">${r.entry_price!=null?r.entry_price.toFixed(2):'–'}</td>
      ${cfdCells('ML',r.id,markers,2)}
      <td class="mono mdl-dim">${r.exit_price!=null?r.exit_price.toFixed(2):'–'}</td>
      <td>${confCell}</td>
      <td class="mono mdl-dim">${r.threshold_used!=null?(r.threshold_used*100).toFixed(0)+'%':'–'}</td>
      <td><span class="tt-chip">${r.horizon_min}m</span></td>
      <td><span class="mdl-ver">${r.model_version||'–'}</span>${conf!=null&&conf>70?' <span class="hi-badge">HIGH</span>':''}</td>
      <td><span class="pill ${r.result}">${r.result}</span></td>
    </tr>`;}).join('');
  }catch(e){}
  try{
    const rows=await fetchJSON('/api/ml/signals?limit=8');
    document.getElementById('mlRecentFeed').innerHTML=rows.length?rows.map(feedRow).join(''):'<div class="empty">ยังไม่มีสัญญาณ</div>';
  }catch(e){}
}


// C-8 perf: เฟด "สัญญาณล่าสุด" บนหน้าภาพรวม — แยกออกมาเพื่อให้ refreshLoop เรียกเฉพาะตอนอยู่แท็บภาพรวม
// (เดิม refreshMlTab ที่เป็นของแท็บ ML อัปเดต feed นี้ด้วย ทำให้หน้าภาพรวมต้องยิงข้อมูลแท็บ ML ทั้งชุด)
async function refreshMlRecentFeed(){
  try{
    const rows=await fetchJSON('/api/ml/signals?limit=8');
    document.getElementById('mlRecentFeed').innerHTML=rows.length?rows.map(feedRow).join(''):'<div class="empty">ยังไม่มีสัญญาณ</div>';
  }catch(e){}
}


export { refreshMlTab, refreshMlRecentFeed };

// C-8: คู่มือใช้งาน ML แบบ dynamic — เกตจริงจาก .env (แนบมากับ /api/ml/latest) + breakeven จาก payout
async function renderMlGuide(stats){
  const gateEl=document.getElementById('mlGuideGate');
  if(!gateEl) return;
  let th=null;
  try{
    const latest=await fetchJSON('/api/ml/latest');
    const g=(latest&&(latest['M1']||latest['M5']))||{};
    if(g.env_threshold!=null) th=Number(g.env_threshold);
    else if(g.threshold_used!=null) th=Number(g.threshold_used);
  }catch(e){}
  const be=(stats&&stats.breakeven!=null)?Number(stats.breakeven):null;
  const gatePct=th!=null?Math.round(th*100):null;
  const hiPct=th!=null?Math.round(Math.min(th+0.10,0.95)*100):null;
  gateEl.textContent=gatePct!=null?gatePct+'%':'–';
  const beEl=document.getElementById('mlGuideBe'); if(beEl) beEl.textContent=be!=null?be+'%':'–';
  const hi=document.querySelector('#mlGuideHigh .mg-range span'); if(hi) hi.textContent=hiPct!=null?hiPct+'%':'–';
  const mid=document.querySelectorAll('#mlGuideMid .mg-range span');
  if(mid[0]) mid[0].textContent=gatePct!=null?gatePct+'%':'–';
  if(mid[1]) mid[1].textContent=(gatePct!=null&&hiPct!=null)?Math.max(hiPct-1,gatePct)+'%':'–';
  const lo=document.querySelector('#mlGuideLow .mg-range span'); if(lo) lo.textContent=gatePct!=null?gatePct+'%':'–';
  // สเกลโซน + หมุดตำแหน่งจริง
  const setW=(id,v)=>{const el=document.getElementById(id); if(el) el.style.width=Math.max(Math.min(v||0,100),0)+'%';};
  const setL=(id,v)=>{const el=document.getElementById(id); if(el) el.style.left=Math.max(Math.min(v||0,100),0)+'%';};
  if(gatePct!=null&&hiPct!=null){
    setW('mlGuideZoneLow',gatePct);
    setW('mlGuideZoneMid',Math.max(hiPct-gatePct,0));
    setW('mlGuideZoneHigh',Math.max(100-hiPct,0));
  }
  setL('mlGuideMarkGate',gatePct);
  setL('mlGuideMarkBe',be);
  // เตือนตรง ๆ เมื่อเกตของระบบต่ำกว่าจุดคุ้มทุน (expected value ติดลบเมื่อ payout ตามจริง)
  const gap=document.getElementById('mlGuideGap');
  if(gap){
    if(gatePct!=null&&be!=null&&gatePct<be){
      gap.style.display=''; gap.textContent=`⚠ เกตต่ำกว่า BE ${(be-gatePct).toFixed(1)} pts`;
    } else { gap.style.display='none'; }
  }
}
