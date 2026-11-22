// ดึงแท่งเทียน + markers แล้ววาดกราฟ — /api/candles, /api/signals/markers, /api/symbol
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2612–2659 แบบ move-only

import { drawLWChart } from './drawLwChart.js';
import { lwChart } from './lwChartInit.js';
import { fetchJSON } from '../../shared/api/client.js';
import { setMarkersCache } from '../../shared/lib/markersCache.js';
import { symbolList } from '../watchlist/index.js';

async function refreshPrice(showLoading=false){
  try{
    const tf=document.querySelector('#tfGroup .tf-btn.active')?.dataset.tf||'1m';
    let sym='';
    const symSel=document.getElementById('chartSymbol');
    if(symSel&&symSel.value) sym=symSel.value;
    if(!sym){ try{ const s=await fetchJSON('/api/symbol'); if(s&&s.symbol){sym=s.symbol;}}catch(e){} }
    if(!sym) sym='frxXAUUSD';
    window.__symSync&&window.__symSync(); // C-14: sync ปุ่ม symbol picker (watchlist เปลี่ยน select ตรง ๆ ก็ตาม)
    const wrap=document.getElementById('lwWrap');
    if(showLoading && wrap) wrap.classList.add('loading');   // ← แสดง loading เฉพาะตอนผู้ใช้กดเปลี่ยน TF/symbol เอง
    // fetch candles + markers พร้อมกัน → เปลี่ยน TF เร็วขึ้น
    // C-4: markers ที่ได้ถูก setMarkersCache ไว้ให้ตารางสัญญาณอ่านด้วย (ไม่ต้องยิง API ซ้ำ)
    const [[prices,markers]]=await Promise.all([
      Promise.all([
        (async()=>{
          let p=await fetchJSON('/api/candles?tf='+tf+'&count=300&symbol='+encodeURIComponent(sym));
          // กรณี Deriv ตอบข้อมูลไม่ครบ → ลองยิง count ใหญ่ขึ้นอีกครั้งกันกราฟเหลือ 1-2 แท่ง
          if(Array.isArray(p)&&p.length<30) p=await fetchJSON('/api/candles?tf='+tf+'&count=1000&symbol='+encodeURIComponent(sym));
          return p;
        })(),
        fetchJSON('/api/signals/markers?symbol='+encodeURIComponent(sym)+'&limit=50').then(m=>{ setMarkersCache(m); return m; }).catch(()=>window._signalMarkers||[])
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
    // C-9 (mockup): เพิ่มลูกศร ▲/▼ หน้า chg
    ce.textContent=`${chg>=0?'▲ +':'▼ −'}${Math.abs(chg).toFixed(2)} (${chgPct>=0?'+':''}${chgPct.toFixed(2)}%)`;
    ce.className='chg '+(chg>=0?'up':'down');
    // C-9 (mockup): สูง/ต่ำช่วง 24 ชม. — คำนวณจากแท่งที่โหลดอยู่แล้ว (ไม่เพิ่ม request / network baseline คงเดิม)
    try{
      const tfSec={'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600,'4h':14400}[tf]||60;
      const n=Math.max(2,Math.floor(86400/tfSec));
      const win=(prices||[]).slice(-n);
      if(win.length){
        const hi=Math.max(...win.map(b=>b.h)), lo=Math.min(...win.map(b=>b.l));
        const hiEl=document.getElementById('pxDayHi'), loEl=document.getElementById('pxDayLo');
        if(hiEl) hiEl.textContent=hi.toFixed(2);
        if(loEl) loEl.textContent=lo.toFixed(2);
      }
    }catch(e){}
    // C-9 (mockup): sym chip — ชื่อย่อ + label จาก symbols.json
    const short=sym.replace(/^frx/,'');
    const subEl=document.getElementById('symbolSub');
    if(subEl){ const meta=symbolList.find(x=>x.symbol===sym); subEl.textContent=meta?(meta.label||short).replace(short+' · ',''):(short); }
    const badge=document.getElementById('symbolBadge'); if(badge) badge.textContent=short;
    // status bar
    const sSym=document.getElementById('statusSym'); if(sSym) sSym.textContent=sym;
    const sTs=document.getElementById('statusTs'); if(sTs) sTs.textContent=new Date().toLocaleTimeString('th-TH');
    const sConn=document.getElementById('statusConn'); if(sConn){ sConn.textContent='● LIVE'; sConn.className='st-ok'; }
    const tTitle=document.getElementById('chartTitle');
    if(tTitle){ const meta=symbolList.find(s=>s.symbol===sym); tTitle.textContent=(meta?meta.label+' — ':'')+'Candlestick'; }
    // C-8: watermark กลางกราฟตามซิมโบลจริง (จางมาก ไม่กวนกราฟ)
    try{ lwChart&&lwChart.applyOptions({watermark:{text:(sym||'').replace(/^frx/,'')}}); }catch(e){}
  }catch(e){
    const sConn=document.getElementById('statusConn');
    if(sConn){ sConn.textContent='● OFFLINE'; sConn.className='st-bad'; }
  }
}


export { refreshPrice };
