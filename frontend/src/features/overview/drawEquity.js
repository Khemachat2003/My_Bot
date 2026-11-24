// กราฟ Equity Curve ในแท็บภาพรวม — C-18: เจาะจง "วันนี้" (เที่ยงคืนท้องถิ่น)
// ประวัติทั้งหมด + เลือกช่วงย้อนหลังอยู่ที่แท็บผลงาน&บันทึก (#equityFullChart)
// C-20: ใช้โหมดเดียวกับแท็บผลงาน (จำใน localStorage — เลือกที่ไหนก็มีผลทั้งสองกราฟ):
//   'pct'   = ผลตอบแทน % จากทุนต้นวัน (เส้นฐาน 0%) — เทียบ CFD (USD) กับ Option (THB) ได้จริง
//   'value' = มูลค่าจริง: CFD แกนขวา ($) / Option แกนซ้าย (THB) — แยกสเกล+หน่วย
// C-19: clamp มุมมองรอบข้อมูลจริง + crosshair TradingView + ป้ายมูลค่าล่าสุด + hover + resize observer

import { _buildEqData, _eqBindClamp, _eqBindResize, _eqGetMode, _eqPctFmt, _eqPctOf, _eqPctPts, _eqRangeStart, _eqSetLast, _eqSlice } from '../../shared/lib/equityData.js';

const CFD_COLOR='#4C8DFF', OPT_COLOR='#9C6FE0', DIM='#4C5566';
const BULL_FILL1='rgba(22,199,132,0.22)', BULL_FILL2='rgba(22,199,132,0.03)';
const BEAR_FILL1='rgba(240,70,92,0.03)',  BEAR_FILL2='rgba(240,70,92,0.22)';

let lwEqChart=null, lwEqSeries=null, lwEqSeries2=null;
let _eqOvCfgKey='';   // mode+base ที่สร้าง series อยู่ (เปลี่ยน → rebuild series)
let _eqOvPrevN=0;     // จำจำนวนจุดรอบก่อน → fit เฉพาะ 0→n
function _eqOvMkSeries(mode,cfdBase,optBase,cur,fmt){
  if(lwEqSeries){ try{ lwEqChart.removeSeries(lwEqSeries); }catch(e){} lwEqSeries=null; }
  if(lwEqSeries2){ try{ lwEqChart.removeSeries(lwEqSeries2); }catch(e){} lwEqSeries2=null; }
  const baseFmt={type:'custom',formatter:_eqPctFmt};
  if(mode==='pct'){
    lwEqSeries=lwEqChart.addBaselineSeries({
      baseValue:{type:'price',price:0},
      lineColor:CFD_COLOR, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM, topFillColor1:BULL_FILL1, topFillColor2:BULL_FILL2,
      bottomLineColor:DIM, bottomLineColor1:DIM, bottomFillColor1:BEAR_FILL1, bottomFillColor2:BEAR_FILL2,
      priceLineVisible:false, lastValueVisible:true, priceFormat:baseFmt,
    });
    lwEqSeries2=lwEqChart.addLineSeries({
      color:OPT_COLOR, lineWidth:2, priceLineVisible:false, lastValueVisible:true, priceFormat:baseFmt,
    });
  } else {
    lwEqSeries=lwEqChart.addBaselineSeries({
      baseValue:{type:'price',price:cfdBase||0}, priceScaleId:'right',
      lineColor:CFD_COLOR, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM, topFillColor1:BULL_FILL1, topFillColor2:BULL_FILL2,
      bottomLineColor:DIM, bottomLineColor1:DIM, bottomFillColor1:BEAR_FILL1, bottomFillColor2:BEAR_FILL2,
      priceLineVisible:false, lastValueVisible:true, priceFormat:{type:'custom',formatter:p=>'$'+fmt(p)},
    });
    lwEqSeries2=lwEqChart.addBaselineSeries({
      baseValue:{type:'price',price:optBase||0}, priceScaleId:'left',
      lineColor:OPT_COLOR, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM, topFillColor1:'rgba(156,111,224,.18)', topFillColor2:'rgba(156,111,224,.03)',
      bottomLineColor:DIM, bottomLineColor1:DIM, bottomFillColor1:'rgba(0,0,0,0)', bottomFillColor2:'rgba(156,111,224,.16)',
      priceLineVisible:false, lastValueVisible:true, priceFormat:{type:'custom',formatter:p=>fmt(p)+' '+cur},
    });
  }
}
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
      rightPriceScale:{borderColor:'#232732',minimumWidth:64},
      leftPriceScale:{visible:false,borderColor:'#232732',minimumWidth:64},
      timeScale:{borderColor:'#232732',rightOffset:6,timeVisible:true,secondsVisible:false},
      crosshair:{
        mode:LightweightCharts.CrosshairMode.Normal,
        vertLine:{color:'rgba(76,141,255,.55)',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#2962FF'},
        horzLine:{color:'rgba(76,141,255,.55)',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#2962FF'},
      },
      handleScroll:{mouseWheel:true,pressedMouseMove:true,horizTouchDrag:true,vertTouchDrag:false,kineticScroll:{touch:true,mouse:false}},
      handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true,axisDoubleClickReset:true},
    });
    _eqBindClamp(lwEqChart);
    _eqBindResize(lwEqChart, el);
  }
  const fmt=p=>Number(p).toLocaleString('th-TH',{maximumFractionDigits:0});
  // ── C-18: ตัดเฉพาะวันนี้ + carry-in เป็นฐาน (บวก/ลบของวันนี้) ──
  const fromTs=_eqRangeStart('today');
  const oS=_eqSlice(b.optPts,fromTs), cS=_eqSlice(b.cfdPts,fromTs);
  const mode=_eqGetMode();
  const isPct=mode==='pct';
  const optDayBase=oS.carry!=null?oS.carry:b.optCapitalBase;
  const cfdDayBase=cS.carry!=null?cS.carry:b.cfdBase;
  const cData=isPct?_eqPctPts(cS.pts,cfdDayBase):cS.pts;
  const oData=isPct?_eqPctPts(oS.pts,optDayBase):oS.pts;
  const hasToday=cData.length+oData.length>0;
  // C-19: จำนวนจุดรวม → ขอบเขตข้อมูลจริงของ clamp
  const unionTs=new Set();
  cData.forEach(p=>unionTs.add(p.time));
  oData.forEach(p=>unionTs.add(p.time));
  _eqSetLast(lwEqChart, unionTs.size);
  // C-20: series ตามโหมด (สร้างใหม่เมื่อโหมด/ฐานเปลี่ยน)
  const cfgKey=mode+'|'+cfdDayBase+'|'+optDayBase+'|'+cur;
  if(cfgKey!==_eqOvCfgKey){ _eqOvMkSeries(mode,cfdDayBase,optDayBase,cur,fmt); _eqOvCfgKey=cfgKey; }
  lwEqChart.applyOptions({leftPriceScale:{visible:mode==='value'}});
  lwEqSeries&&lwEqSeries.setData(cData);
  lwEqSeries2&&lwEqSeries2.setData(oData);
  lwEqChart.applyOptions({width:el.clientWidth||300,height:el.clientHeight||260});
  // C-18: fit เฉพาะตอนข้อมูลวันนี้มาถึงครั้งแรก (0→n) — รอบถัดไปรักษา zoom/pan ผู้ใช้
  if(hasToday&&_eqOvPrevN===0) lwEqChart.timeScale().fitContent();
  _eqOvPrevN=cData.length+oData.length;
  // ── C-19/C-20: hover อ่านค่า — pct: %+มูลค่าจริง · value: มูลค่าจริง ──
  if(!lwEqChart.__eqHoverBound){
    lwEqChart.__eqHoverBound=true;
    lwEqChart.subscribeCrosshairMove(param=>{
      const hEl=document.getElementById('eqHoverOv'); if(!hEl) return;
      if(!param||param.time==null){ hEl.innerHTML=''; return; }
      const dTxt=new Date(param.time*1000).toLocaleString('th-TH',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
      const modeNow=_eqGetMode();
      const rows=[];
      const read=(ser,map,absBase,unit)=>{
        const pt=ser?param.seriesData.get(ser):null;
        if(!pt||pt.value==null) return;
        const label=unit==='cfd'?`<b style="color:${CFD_COLOR}">CFD</b>`:`<b style="color:${OPT_COLOR}">Option</b>`;
        if(modeNow==='pct'){
          const cls=pt.value>0?'eq-up':(pt.value<0?'eq-dn':'');
          let absTxt='';
          const abs=map.get(param.time);
          if(abs!=null){
            const pnl=abs-absBase;
            absTxt=` <span class="h-abs">(${unit==='cfd'?'$':''}${fmt(abs)}${unit==='cfd'?'':' '+cur} · ${pnl>=0?'+':''}${fmt(pnl)})</span>`;
          }
          rows.push(`${label} <span class="${cls}">${_eqPctFmt(pt.value)}</span>${absTxt}`);
        } else {
          const pnl=pt.value-absBase;
          const cls=pnl>0?'eq-up':(pnl<0?'eq-dn':'');
          rows.push(`${label} <span class="${cls}">${unit==='cfd'?'$':''}${fmt(pt.value)}${unit==='cfd'?'':' '+cur} (${pnl>=0?'+':''}${fmt(pnl)})</span>`);
        }
      };
      read(lwEqSeries,new Map(cS.pts.map(p=>[p.time,p.value])),cfdDayBase,'cfd');
      read(lwEqSeries2,new Map(oS.pts.map(p=>[p.time,p.value])),optDayBase,'opt');
      hEl.innerHTML=rows.length?`<span class="eq-h-time">${dTxt}</span>${rows.join('<span style="color:var(--border)"> · </span>')}`:'';
    });
  }
  if(emptyEl) emptyEl.style.display=hasToday?'none':'block';
  if(statsEl){
    // C-20: ชิป — ป้ายชื่อเส้นติดสีเส้นจริง · % ใช้ฐานต้นวัน + guard ฐานเล็ก/ติดลบ (ไม่โชว์ % เพี้ยน)
    const pnlChip=(pnl,base)=>{
      const pc=_eqPctOf(pnl,base);
      const pctTxt=pc!=null?` · ${pc>0?'+':''}${pc.toFixed(1)}%`:'';
      if(pnl>0) return `<span class="eq-up">(+${fmt(pnl)}${pctTxt})</span>`;
      if(pnl<0) return `<span class="eq-dn">(${fmt(pnl)}${pctTxt})</span>`;
      return `<span>(0)</span>`;
    };
    const chips=['<span class="eq-scope">วันนี้</span>'];
    if(cS.n){
      const lastV=cS.pts[cS.pts.length-1].value, pnl=lastV-cfdDayBase;
      chips.push(`<b style="color:${CFD_COLOR}">CFD</b> $${fmt(lastV)} ${pnlChip(pnl,cfdDayBase)} · ${cS.n} เทรด`);
    }
    if(oS.n){
      const lastV=oS.pts[oS.pts.length-1].value, pnl=lastV-optDayBase;
      chips.push(`<b style="color:${OPT_COLOR}">Option</b> ${fmt(lastV)} ${cur} ${pnlChip(pnl,optDayBase)} · ${oS.n} เทรด`);
    }
    if(chips.length===1) chips.push('ยังไม่มีเทรดที่จบวันนี้ — ดูประวัติทั้งหมดที่แท็บผลงาน&บันทึก');
    statsEl.innerHTML=chips.join('<span class="eq-sep">|</span>');
  }
}


export { drawEquity };
