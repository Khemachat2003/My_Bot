// research แตะ EMA200 — /api/ticktouch/stats
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2897–2952 แบบ move-only
// (C-6 — ปรับเฉพาะสีตาม design_system Section 6: TT_CASE_COLORS ตัด cyan/yellow/green
//  → accent/warn/bull · WR 2 จุดใช้ wrColor(wr,60,50) จาก C-5 · ทิศเป็น badge แบบตารางหลัก C-4)

import { fetchJSON } from '../../shared/api/client.js';
import { wrColor } from '../../shared/lib/pnlText.js';
import { fmtTime } from '../../shared/lib/formatTime.js';

const TT_CASE_COLORS={'TICK_TOUCH':'var(--accent)','WICK_BOUNCE':'var(--warn)','BREAKOUT':'var(--bull)'};
const TT_COND_NAMES={
  'c1_fractal_sr':'1. Fractal S/R','c2_bb_break':'2. BB Break','c3_rsi_ob_os':'3. RSI OVB/OVS',
  'c4_rsi_div':'4. RSI Divergence','c5_adx':'5. ADX > 20','c6_pa':'6. PA Confirmation',
  'c7_fractal_trend':'7. Fractal Trend','c8_grip':'8. Grip','c9_bb_width':'9. BB Width',
  'c10_mtf':'10. MTF Trend','c11_ema_slope':'11. EMA Slope',
};

// badge ทิศทาง — markup เดียวกับตารางหลัก C-4 (CSS .dir-badge ใน shared/ui/tables.css)
function dirBadge(d){
  if(d==='CALL'||d==='BUY') return `<span class="dir-badge call">▲ ${d}</span>`;
  if(d==='PUT'||d==='SELL') return `<span class="dir-badge put">▼ ${d}</span>`;
  return '<span class="dir-badge wait">○ รอ</span>';
}

async function refreshTickTouchResearch(){
  try{
    const s=await fetchJSON('/api/ticktouch/stats');
    // Case cards — C-8 premium: tile มีแถบสีบน + WR ใหญ่ + สรุป W/L
    const cards=document.getElementById('ttCaseCards');
    if(cards){
      const cases=Object.entries(s.by_case||{});
      const card=(k,v,col)=>`
        <div class="tt-card" style="--case:${col};">
          <div class="tt-case">${k}</div>
          <div class="tt-wr" style="color:var(--${wrColor(v.wr,60,50)});">${v.wr}%</div>
          <div class="tt-meta">${v.wins}W / ${v.losses}L · ${v.n} ไม้</div>
        </div>`;
      cards.innerHTML=cases.length?cases.map(([k,v])=>card(k,v,TT_CASE_COLORS[k]||'var(--border)')).join('')
        +`<div class="tt-card tt-total" style="--case:var(--border);">
            <div class="tt-case">TOTAL</div>
            <div class="tt-wr">${s.wr||0}%</div>
            <div class="tt-meta">${s.wins}W · ${s.resolved} resolved · ⏳${s.pending}</div>
          </div>`
        :'<div class="empty" style="grid-column:1/-1;">ยังไม่มีข้อมูล research — รอราคาแตะ EMA200</div>';
    }
    // Condition vote table — WR เป็นแถบเทียบกัน
    const condBody=document.querySelector('#ttCondTable tbody');
    if(condBody){
      const conds=Object.entries(s.by_condition||{})
        .sort((a,b)=>(b[1].wr_when_true||0)-(a[1].wr_when_true||0));
      condBody.innerHTML=conds.length?conds.map(([k,v])=>{
        const col=wrColor(v.wr_when_true,60,50);
        return `<tr>
          <td>${TT_COND_NAMES[k]||k}</td>
          <td class="mono mdl-dim">${v.true_n}</td>
          <td class="mono mdl-dim">${v.true_wins}</td>
          <td><span class="mdl-meter"><span class="dl-track"><i style="width:${Math.min(v.wr_when_true,100)}%;background:var(--${col})"></i></span><b style="color:var(--${col})">${v.wr_when_true}%</b></span></td>
          <td class="mono mdl-dim">${v.false_n?v.wr_when_false+'%':'–'}</td>
        </tr>`;}).join(''):'<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:14px;">รอข้อมูล resolved</td></tr>';
    }
    // Recent touches — case chip + จำนวน checklist chip
    const recBody=document.querySelector('#ttRecentTable tbody');
    if(recBody){
      const rec=s.recent||[];
      recBody.innerHTML=rec.length?rec.map(r=>`
        <tr>
          <td class="mono mdl-dim">${fmtTime(r.signal_time)}</td>
          <td><b>${(r.symbol||'').replace('frx','')}</b></td>
          <td><span class="tt-chip" style="color:${TT_CASE_COLORS[r.touch_case]||'var(--muted)'};border-color:currentColor;">${(r.touch_case||'').replace('_TOUCH','').replace('_',' ')}</span></td>
          <td>${dirBadge(r.direction)}</td>
          <td class="mono">${r.entry_price?.toFixed(2)}</td>
          <td class="mono mdl-dim">${r.exit_price!=null?r.exit_price.toFixed(2):'–'}</td>
          <td><span class="tt-chip">${r.passed_count}/10</span></td>
          <td><span class="pill ${r.result}">${r.result}</span></td>
        </tr>`).join(''):'<tr><td colspan="8" style="color:var(--muted);text-align:center;padding:14px;">ยังไม่มีเหตุการณ์แตะ</td></tr>';
    }
  }catch(e){}
}


export { refreshTickTouchResearch };
