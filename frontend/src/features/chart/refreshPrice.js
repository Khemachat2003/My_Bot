// ดึงแท่งเทียน + markers แล้ววาดกราฟ — /api/candles, /api/signals/markers, /api/symbol
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2612–2659 แบบ move-only

import { drawLWChart } from './drawLwChart.js';
import { fetchJSON } from '../../shared/api/client.js';
import { symbolList } from '../watchlist/index.js';

async function refreshPrice(showLoading=false){
  try{
    const tf=document.querySelector('#tfGroup .tf-btn.active')?.dataset.tf||'1m';
    let sym='';
    const symSel=document.getElementById('chartSymbol');
    if(symSel&&symSel.value) sym=symSel.value;
    if(!sym){ try{ const s=await fetchJSON('/api/symbol'); if(s&&s.symbol){sym=s.symbol;}}catch(e){} }
    if(!sym) sym='frxXAUUSD';
    const badge=document.getElementById('symbolBadge'); if(badge) badge.textContent=sym;
    const wrap=document.getElementById('lwWrap');
    if(showLoading && wrap) wrap.classList.add('loading');   // ← แสดง loading เฉพาะตอนผู้ใช้กดเปลี่ยน TF/symbol เอง
    // fetch candles + markers พร้อมกัน → เปลี่ยน TF เร็วขึ้น
    const [[prices,markers]]=await Promise.all([
      Promise.all([
        (async()=>{
          let p=await fetchJSON('/api/candles?tf='+tf+'&count=300&symbol='+encodeURIComponent(sym));
          // กรณี Deriv ตอบข้อมูลไม่ครบ → ลองยิง count ใหญ่ขึ้นอีกครั้งกันกราฟเหลือ 1-2 แท่ง
          if(Array.isArray(p)&&p.length<30) p=await fetchJSON('/api/candles?tf='+tf+'&count=1000&symbol='+encodeURIComponent(sym));
          return p;
        })(),
        fetchJSON('/api/signals/markers?symbol='+encodeURIComponent(sym)+'&limit=50').catch(()=>window._signalMarkers||[])
      ])
    ]);
    if(wrap) wrap.classList.remove('loading');
    if(!prices||!prices.length) return;
    if(Array.isArray(markers)) window._signalMarkers=markers;
    drawLWChart(prices,markers,tf);
    const last=prices[prices.length-1], prev=prices[prices.length-2];
    const chg=prev?last.c-prev.c:0;
    const chgPct=prev?chg/prev.c*100:0;
    const pe=document.getElementById('tickerPrice');
    pe.textContent=last.c.toFixed(2);
    pe.className='price '+(chg>=0?'up':'down');
    const ce=document.getElementById('tickerChg');
    ce.textContent=`${chg>=0?'+':''}${chg.toFixed(2)} (${chgPct>=0?'+':''}${chgPct.toFixed(2)}%)`;
    ce.className='chg '+(chg>=0?'up':'down');
    // status bar
    const sSym=document.getElementById('statusSym'); if(sSym) sSym.textContent=sym;
    const sTs=document.getElementById('statusTs'); if(sTs) sTs.textContent=new Date().toLocaleTimeString('th-TH');
    const sConn=document.getElementById('statusConn'); if(sConn){ sConn.textContent='● LIVE'; sConn.className='st-ok'; }
    const tTitle=document.getElementById('chartTitle');
    if(tTitle){ const meta=symbolList.find(s=>s.symbol===sym); tTitle.textContent=(meta?meta.label+' — ':'')+'Candlestick'; }
  }catch(e){
    const sConn=document.getElementById('statusConn');
    if(sConn){ sConn.textContent='● OFFLINE'; sConn.className='st-bad'; }
  }
}


export { refreshPrice };
