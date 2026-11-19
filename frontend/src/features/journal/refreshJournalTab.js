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
    const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const maxAbs=Math.max(1,...daily.map(d=>Math.abs(d.pnl||0)));
    const be=j.breakeven;
    const tb=document.querySelector('#dailyTable tbody');
    if(!daily.length){
      tb.innerHTML='<tr><td colspan="5" class="empty">ยังไม่มีข้อมูล</td></tr>';
    } else {
      const rows=daily.map(d=>{
        const pnl=d.pnl||0;
        const dirCls=pnl>0?'bull':(pnl<0?'bear':'muted');
        const wrCol=wrColor(d.winrate, be);
        const barW=Math.min(Math.abs(pnl)/maxAbs*50,50);           // ครึ่งความกว้างสูงสุด (ซ้าย/ขวาจากศูนย์กลาง)
        const side=pnl>=0?'left:50%':'right:50%';
        const [y,m,dd]=String(d.day||'').split('-');
        const dLabel=(m&&dd)?`${dd} ${MON[(+m)-1]||''}`:(d.day||'');
        return `<tr>
          <td class="dl-day"><span class="dl-date">${dLabel}</span><span class="dl-yr">${y||''}</span></td>
          <td class="mono dl-n">${d.n}</td>
          <td class="mono dl-w">${d.wins}</td>
          <td class="dl-wr"><span class="dl-track">${be!=null?`<u style="left:${Math.min(be,100)}%"></u>`:''}<i style="width:${Math.min(d.winrate,100)}%;background:var(--${wrCol})"></i></span><b style="color:var(--${wrCol})">${d.winrate}%</b></td>
          <td class="dl-pnl"><span class="dl-pnl-val" style="color:var(--${dirCls})">${pnlText(d.pnl,{fixed:true,digits:2})}</span><span class="dl-track dl-track-pnl"><em></em><i style="width:${barW}%;${side};background:var(--${dirCls})"></i></span></td>
        </tr>`;
      }).join('');
      const tN=daily.reduce((a,b)=>a+(b.n||0),0);
      const tW=daily.reduce((a,b)=>a+(b.wins||0),0);
      const tP=daily.reduce((a,b)=>a+(b.pnl||0),0);
      const tWr=tN?+(tW/tN*100).toFixed(1):0;
      const tCls=tP>0?'bull':(tP<0?'bear':'muted');
      const total=`<tr class="dl-total">
          <td class="dl-day"><span class="dl-date">รวม ${daily.length} วัน</span></td>
          <td class="mono dl-n">${tN}</td>
          <td class="mono dl-w">${tW}</td>
          <td class="dl-wr"><b>${tWr}%</b></td>
          <td class="dl-pnl"><span class="dl-pnl-val" style="color:var(--${tCls})">${pnlText(tP,{fixed:true,digits:2})}</span></td>
        </tr>`;
      tb.innerHTML=rows+total;
    }
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
