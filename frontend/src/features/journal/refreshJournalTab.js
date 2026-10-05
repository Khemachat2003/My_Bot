// แท็บ Journal — /api/journal/stats, /api/models
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3083–3122 แบบ move-only
// TODO: ย้ายไป backend — ค่า base 5000 ของ CFD equity hard-code ฝั่งหน้าเว็บ

import { drawEquityFull } from './drawEquityFull.js';
import { fetchJSON } from '../../shared/api/client.js';
import { renderStat } from '../../shared/ui/domText.js';
import { pnlText, wrColor } from '../../shared/lib/pnlText.js';

async function refreshJournalTab(){
  try{
    const j=await fetchJSON('/api/journal/stats');
    const wr = j.winrate || 0;
    // C-5 (5.3): สี winrate ตาม breakeven จาก API — >= breakeven → bull, ต่ำกว่า → bear (ไม่มีข้อมูล → muted)
    renderStat(document.getElementById('jWr'), wr+'%', j.n?wrColor(j.winrate, j.breakeven):'muted');
    document.getElementById('jWrSub').textContent = j.n
      ? `${j.wins}W / ${j.losses}L · ${j.daily.length} วัน · CI [${j.ci_low}%–${j.ci_high}%]`
      : 'ยังไม่มีผล';
    let set0={};
    let cfdData={points:[]};
    try{
      set0=await fetchJSON('/api/journal/settings')||{};
      const cp=await fetchJSON('/api/cfd/paper')||{};
      cfdData={points:(cp.trades||[]).filter(t=>t.exit_time), base:5000};
    }catch(e){}
    drawEquityFull({
      opt:{points:j.equity||[], capital:set0.capital||0, stake:set0.stake||1, cur:set0.currency||'THB'},
      cfd:cfdData,
    });
    const daily=j.daily||[];
    document.querySelector('#dailyTable tbody').innerHTML=daily.map(d=>`
      <tr><td>${d.day}</td><td class="mono">${d.n}</td><td class="mono">${d.wins}</td><td class="mono">${d.winrate}%</td>
      <td class="mono ${d.pnl>0?'dir-call':(d.pnl<0?'dir-put':'')}">${pnlText(d.pnl,{fixed:true,digits:2})}</td></tr>`).join('')
      || '<tr><td colspan="5" class="empty">ยังไม่มีข้อมูล</td></tr>';
  }catch(e){}
  try{
    const models=await fetchJSON('/api/models');
    document.querySelector('#modelTable tbody').innerHTML=models.map(m=>`
      <tr>
        <td><b>${m.model_key}</b></td>
        <td>${m.version}</td>
        <td class="mono">${m.horizon}</td>
        <td class="mono">${m.n_rows||'–'}</td>
        <td class="mono">${m.auc_test!=null?m.auc_test:'–'}</td>
        <td class="mono">${m.chosen_conf!=null?m.chosen_conf:'–'}</td>
        <td style="font-size:10px;color:var(--muted)">${m.feature_set||'–'}</td>
      </tr>`).join('') || '<tr><td colspan="7" class="empty">ยังไม่มีโมเดลที่ลงทะเบียน</td></tr>';
  }catch(e){}
}


export { refreshJournalTab };
