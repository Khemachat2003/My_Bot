// สถิติแท็บภาพรวม — /api/ml/stats, /api/stats, /api/journal/stats|settings, /api/cfd/paper, /api/models
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1956–1995 แบบ move-only
// TODO: ย้ายไป backend — ค่า base 5000 ของ CFD equity hard-code ฝั่งหน้าเว็บ

import { drawEquity } from './drawEquity.js';
import { fetchJSON } from '../../shared/api/client.js';
import { fmtMargin } from '../../shared/lib/formatSignal.js';
import { elText, elTextCls, renderStat } from '../../shared/ui/domText.js';

async function refreshOverview(){
  try{
    const ml=await fetchJSON('/api/ml/stats');
    renderStat(document.getElementById('ovMlWinrate'),ml.n_resolved?ml.winrate+'%':'–',ml.n_resolved?'cyan':'muted');
    elText('ovMlWinrateSub',ml.n_resolved?`CI [${ml.ci_low}% – ${ml.ci_high}%]`:'รอสัญญาณ...');
    elText('ovMlMargin',ml.n_resolved?fmtMargin(ml.margin):'–');
    elText('ovMlN',`${ml.n_resolved} W/L = ${ml.wins}/${ml.losses}`);
  }catch(e){}
  try{
    const st=await fetchJSON('/api/stats');
    renderStat(document.getElementById('ovSetWinrate'),st.n_resolved?st.winrate+'%':'–',st.n_resolved?'blue':'muted');
    elText('ovSetWinrateSub',st.n_resolved?`CI [${st.ci_low}% – ${st.ci_high}%]`:'รอสัญญาณ...');
    elText('ovSetMargin',st.n_resolved?fmtMargin(st.margin):'–');
    elText('ovSetN',`${st.n_resolved} W/L = ${st.wins}/${st.losses}`);
  }catch(e){}
  try{
    const j=await fetchJSON('/api/journal/stats');
    elTextCls('ovPnl',j.total_pnl==null?'–':((j.total_pnl>0?'+':'')+j.total_pnl.toFixed(2)),
      'val '+(j.total_pnl>0?'green':(j.total_pnl<0?'red':'muted')));
    elText('ovPnlSub',`${j.n} trades · ชนะ ${j.wins} / แพ้ ${j.losses}`);
    let set0={};
    let cfdData={points:[]};
    try{
      set0=await fetchJSON('/api/journal/settings')||{};
      const cp=await fetchJSON('/api/cfd/paper')||{};
      cfdData={points:(cp.trades||[]).filter(t=>t.exit_time), base:5000};
    }catch(e){}
    drawEquity({
      opt:{points:j.equity||[], capital:set0.capital||0, stake:set0.stake||1, cur:set0.currency||'THB'},
      cfd:cfdData,
    });
  }catch(e){}
  try{
    const reg=await fetchJSON('/api/models');
    const m1=reg.find(r=>r.model_key==='M1'), m5=reg.find(r=>r.model_key==='M5');
    if(m1){ elTextCls('ovModelM1',m1.version,'val purple'); elText('ovModelM1Sub',`AUC ${m1.auc_test} · conf ${m1.chosen_conf}`); }
    if(m5){ elTextCls('ovModelM5',m5.version,'val purple'); elText('ovModelM5Sub',`AUC ${m5.auc_test} · conf ${m5.chosen_conf}`); }
  }catch(e){}
}


export { refreshOverview };
