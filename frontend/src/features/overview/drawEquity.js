// กราฟ Equity Curve ในแท็บภาพรวม — C-18: เจาะจง "วันนี้" (เที่ยงคืนท้องถิ่น)
// ประวัติทั้งหมด + เลือกช่วงย้อนหลังอยู่ที่แท็บผลงาน&บันทึก (#equityFullChart)
// Phase C-3 (design_system 5.1): เส้นเดียวสี --accent + fill เหนือฐาน --bull-dim / ใต้ฐาน --bear-dim
// C-18: baseline = ทุน "ตอนเริ่มวัน" (carry-in เมื่อวาน) → fill เขียว/แดง = บวก/ลบของวันนี้
// C-18: เลิก fitContent ทุกรอบ refresh — fit เฉพาะตอนข้อมูลวันนี้มาถึงครั้งแรก (0→n)
//       แล้วรักษา zoom/pan ที่ผู้ใช้ตั้งไว้ (เดิมเด้งกลับทุก 5 วิ — "การย่อกราฟเพี้ยน" ตามที่ผู้ใช้เจอ)

import { _buildEqData, _eqRangeStart, _eqSlice } from '../../shared/lib/equityData.js';

const ACCENT='#4C8DFF', DIM='#4C5566';
const BULL_FILL1='rgba(22,199,132,0.22)', BULL_FILL2='rgba(22,199,132,0.03)';
const BEAR_FILL1='rgba(240,70,92,0.03)',  BEAR_FILL2='rgba(240,70,92,0.22)';

let lwEqChart=null, lwEqSeries=null, lwEqSeries2=null;
let lwEqBase=null, lwEqBase2=null; // base ปัจจุบันของแต่ละ series (เปลี่ยน → สร้างใหม่)
let _eqOvPrevN=0;                  // จำจำนวนเทรดวันนี้รอบก่อน → fit เฉพาะ 0→n
function drawEquity(payload){
  const el=document.getElementById('equityChart'); if(!el) return;
  const b=_buildEqData(payload&&payload.opt, payload&&payload.cfd);
  const cur=(payload&&payload.opt&&payload.opt.cur)||'THB';
  const statsEl=document.getElementById('eqStatsOv');
  const emptyEl=document.getElementById('eqEmptyOv');
  if(!window.LightweightCharts) return;
  if(!lwEqChart){
    lwEqChart=LightweightCharts.createChart(el,{
      height:el.clientHeight||260, width:el.clientWidth||300,
      layout:{background:{color:'transparent'},textColor:'#838B9C',fontFamily:'IBM Plex Mono, monospace'},
      grid:{vertLines:{color:'#1A1D27'},horzLines:{color:'#1A1D27'}},
      rightPriceScale:{borderColor:'#232732'},
      // C-18: มุมมอง "วันนี้" ต้องเห็นเวลาในแกน (ไม่ใช่แค่วันที่ซ้ำกันทั้งแกน)
      timeScale:{borderColor:'#232732',rightOffset:2,timeVisible:true,secondsVisible:false},
    });
    window.addEventListener('resize',()=>{ if(lwEqChart&&el.clientWidth>0) lwEqChart.applyOptions({width:el.clientWidth}); });
  }
  const fmt=p=>Number(p).toLocaleString('th-TH',{maximumFractionDigits:0});
  // ── C-18: ตัดเฉพาะวันนี้ + carry-in เป็นฐาน (บวก/ลบของวันนี้) ──
  const fromTs=_eqRangeStart('today');
  const oS=_eqSlice(b.optPts,fromTs), cS=_eqSlice(b.cfdPts,fromTs);
  const hasToday=oS.n+cS.n>0;
  const optDayBase=oS.carry!=null?oS.carry:b.optCapitalBase;
  const cfdDayBase=cS.carry!=null?cS.carry:b.cfdBase;
  // สร้าง baseline series ใหม่เมื่อยังไม่มี หรือ base เปลี่ยน (เช่นข้ามวัน → carry เปลี่ยน)
  const mkSeries=(existing,curBase,prevBase,priceFmt)=>{
    if(existing&&prevBase===(curBase||0)) return existing;
    if(existing) lwEqChart.removeSeries(existing);
    return lwEqChart.addBaselineSeries({
      baseValue:{type:'price',price:curBase||0},
      lineColor:ACCENT, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM,
      topFillColor1:BULL_FILL1, topFillColor2:BULL_FILL2,
      bottomLineColor:DIM, bottomLineColor1:DIM,
      bottomFillColor1:BEAR_FILL1, bottomFillColor2:BEAR_FILL2,
      priceLineVisible:false, lastValueVisible:false, priceFormat:priceFmt,
    });
  };
  if(cS.n){
    lwEqSeries=mkSeries(lwEqSeries,cfdDayBase,lwEqBase,{type:'custom',formatter:p=>'$'+fmt(p)});
    lwEqBase=cfdDayBase||0;
  }
  if(oS.n){
    lwEqSeries2=mkSeries(lwEqSeries2,optDayBase,lwEqBase2,{type:'custom',formatter:p=>fmt(p)+' '+cur});
    lwEqBase2=optDayBase||0;
  }
  if(lwEqSeries) lwEqSeries.setData(cS.n?cS.pts:[]);
  if(lwEqSeries2) lwEqSeries2.setData(oS.n?oS.pts:[]);
  lwEqChart.applyOptions({width:el.clientWidth||300,height:el.clientHeight||260});
  // C-18: fit เฉพาะตอนข้อมูลวันนี้มาถึงครั้งแรก (0→n) — รอบถัดไปรักษา zoom/pan ผู้ใช้
  if(hasToday&&_eqOvPrevN===0) lwEqChart.timeScale().fitContent();
  _eqOvPrevN=oS.n+cS.n;
  if(emptyEl) emptyEl.style.display=hasToday?'none':'block';
  if(statsEl){
    // chips ขอบเขต "วันนี้" — P&L นับจากทุนตอนเริ่มวัน (carry-in) ไม่ใช่ทุนตั้งต้นตอนเปิดพอร์ต
    const pnlChip=(pnl,base)=>{
      if(pnl>0) return `<span class="eq-up">(+${fmt(pnl)} · +${(pnl/Math.max(base,1)*100).toFixed(1)}%)</span>`;
      if(pnl<0) return `<span class="eq-dn">(${fmt(pnl)} · ${(pnl/Math.max(base,1)*100).toFixed(1)}%)</span>`;
      return `<span>(0)</span>`;
    };
    const chips=['<span class="eq-scope">วันนี้</span>'];
    if(cS.n){
      const lastV=cS.pts[cS.pts.length-1].value, pnl=lastV-cfdDayBase;
      chips.push(`CFD <b>$${fmt(lastV)}</b> ${pnlChip(pnl,cfdDayBase)} · ${cS.n} เทรด`);
    }
    if(oS.n){
      const lastV=oS.pts[oS.pts.length-1].value, pnl=lastV-optDayBase;
      chips.push(`Option <b>${fmt(lastV)} ${cur}</b> ${pnlChip(pnl,optDayBase)} · ${oS.n} เทรด`);
    }
    if(chips.length===1) chips.push('ยังไม่มีเทรดที่จบวันนี้ — ดูประวัติทั้งหมดที่แท็บผลงาน&บันทึก');
    statsEl.innerHTML=chips.join('<span style="color:var(--border)"> | </span>');
  }
}


export { drawEquity };
