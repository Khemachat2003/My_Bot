// research แตะ EMA200 — /api/ticktouch/stats
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2897–2952 แบบ move-only

import { fetchJSON } from '../../shared/api/client.js';
import { dirClass } from '../../shared/lib/formatSignal.js';
import { fmtTime } from '../../shared/lib/formatTime.js';

const TT_CASE_COLORS={'TICK_TOUCH':'var(--cyan)','WICK_BOUNCE':'var(--yellow)','BREAKOUT':'var(--green)'};
const TT_COND_NAMES={
  'c1_fractal_sr':'1. Fractal S/R','c2_bb_break':'2. BB Break','c3_rsi_ob_os':'3. RSI OVB/OVS',
  'c4_rsi_div':'4. RSI Divergence','c5_adx':'5. ADX > 20','c6_pa':'6. PA Confirmation',
  'c7_fractal_trend':'7. Fractal Trend','c8_grip':'8. Grip','c9_bb_width':'9. BB Width',
  'c10_mtf':'10. MTF Trend','c11_ema_slope':'11. EMA Slope',
};

async function refreshTickTouchResearch(){
  try{
    const s=await fetchJSON('/api/ticktouch/stats');
    // Case cards
    const cards=document.getElementById('ttCaseCards');
    if(cards){
      const cases=Object.entries(s.by_case||{});
      cards.innerHTML=cases.length?cases.map(([k,v])=>`
        <div style="background:var(--bg);border:1px solid ${TT_CASE_COLORS[k]||'var(--border)'};border-radius:8px;padding:10px;text-align:center;">
          <div style="font-size:11px;color:var(--muted);">${TT_CASE_COLORS[k]?k:'–'}</div>
          <div style="font-size:20px;font-weight:800;color:${v.wr>=60?'var(--green)':(v.wr>=50?'var(--yellow)':'var(--red)')};">${v.wr}%</div>
          <div style="font-size:11px;color:var(--muted);">${v.wins}W / ${v.losses}L (${v.n})</div>
        </div>`).join('')+'<div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px;text-align:center;"><div style="font-size:11px;color:var(--muted);">TOTAL</div><div style="font-size:20px;font-weight:800;">'+(s.wr||0)+'%</div><div style="font-size:11px;color:var(--muted);">'+s.wins+'W ('+s.resolved+') · ⏳'+s.pending+'</div></div>'
        :'<div class="empty" style="grid-column:1/-1;">ยังไม่มีข้อมูล research — รอราคาแตะ EMA200</div>';
    }
    // Condition vote table
    const condBody=document.querySelector('#ttCondTable tbody');
    if(condBody){
      const conds=Object.entries(s.by_condition||{})
        .sort((a,b)=>(b[1].wr_when_true||0)-(a[1].wr_when_true||0));
      condBody.innerHTML=conds.length?conds.map(([k,v])=>`
        <tr>
          <td>${TT_COND_NAMES[k]||k}</td>
          <td>${v.true_n}</td>
          <td>${v.true_wins}</td>
          <td><b style="color:${v.wr_when_true>=60?'var(--green)':(v.wr_when_true>=50?'var(--yellow)':'var(--red)')}">${v.wr_when_true}%</b></td>
          <td style="color:var(--muted);">${v.false_n?v.wr_when_false+'%':'–'}</td>
        </tr>`).join(''):'<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:14px;">รอข้อมูล resolved</td></tr>';
    }
    // Recent touches
    const recBody=document.querySelector('#ttRecentTable tbody');
    if(recBody){
      const rec=s.recent||[];
      recBody.innerHTML=rec.length?rec.map(r=>`
        <tr>
          <td>${fmtTime(r.signal_time)}</td>
          <td>${(r.symbol||'').replace('frx','')}</td>
          <td style="color:${TT_CASE_COLORS[r.touch_case]||'inherit'};">${(r.touch_case||'').replace('_TOUCH','').replace('_',' ')}</td>
          <td class="${dirClass(r.direction)}">${r.direction}</td>
          <td class="mono">${r.entry_price?.toFixed(2)}</td>
          <td class="mono">${r.exit_price!=null?r.exit_price.toFixed(2):'–'}</td>
          <td class="mono">${r.passed_count}/10</td>
          <td><span class="pill ${r.result}">${r.result}</span></td>
        </tr>`).join(''):'<tr><td colspan="8" style="color:var(--muted);text-align:center;padding:14px;">ยังไม่มีเหตุการณ์แตะ</td></tr>';
    }
  }catch(e){}
}


export { refreshTickTouchResearch };
