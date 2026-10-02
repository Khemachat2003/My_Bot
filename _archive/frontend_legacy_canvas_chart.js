// ARCHIVE — กราฟ canvas รุ่นเก่า + S/R แบบ canvas (ถูกแทนด้วย lightweight-charts แล้ว ไม่มีโค้ดใดเรียก)
// ย้ายจาก index.html เดิม บรรทัด 1205–1216, 1219–1222, 1224–1245, 1309–1907 — ไม่ถูก import ที่ไหน เก็บไว้รอผู้ใช้อนุญาตให้ลบ

/* ═══════ CANDLESTICK + VOLUME + EMA (pure canvas) ═══════ */
function ema(vals, period){
  const out=new Array(vals.length).fill(null);
  if(!vals.length) return out;
  const k=2/(period+1); let prev=vals[0];
  for(let i=0;i<vals.length;i++){
    prev=(i===0)?vals[0]:vals[i]*k+prev*(1-k);
    out[i]=prev;
  }
  return out;
}
const chartView={count:300,end:-1}; // end=-1 = ล็อกกับแท่งล่าสุด; แก้ด้วย zoom/pan
let chartGeom=null;     // geometry ล่าสุดจาก drawCandles (pxForData/py/ยอดบรรทัด) ไว้ใช้ crosshair
let crosshair=null;     // {x, y} พิกัดเมาส์บน canvas; null = ไม่มี crosshair
let chartCursor='default';

function sma(vals, period){
  const out=new Array(vals.length).fill(null); let sum=0;
  for(let i=0;i<vals.length;i++){
    sum+=vals[i];
    if(i>=period) sum-=vals[i-period];
    if(i>=period-1) out[i]=sum/period;
  }
  return out;
}
function stdev(vals, period){
  const out=new Array(vals.length).fill(null);
  for(let i=period-1;i<vals.length;i++){
    const slice=vals.slice(i-period+1,i+1);
    const mean=slice.reduce((a,b)=>a+b,0)/period;
    out[i]=Math.sqrt(slice.reduce((a,b)=>a+(b-mean)**2,0)/period);
  }
  return out;
}
function bollinger(closes, period=20, mult=2){
  const mid=sma(closes,period), sd=stdev(closes,period);
  return { mid, up:closes.map((_,i)=>mid[i]==null?null:mid[i]+mult*sd[i]), low:closes.map((_,i)=>mid[i]==null?null:mid[i]-mult*sd[i]) };
}
function drawCandles(canvas, data){
  if(!canvas||!canvas.getContext){ return; }
  lastCandles=data;
  // กราฟหลักถูกแทนด้วย lightweight-charts (drawLWChart) แล้ว ฟังก์ชันนี้คงไว้เป็น fallback/inert
  {
  const dpr=window.devicePixelRatio||1;
  const rect=canvas.getBoundingClientRect();
  canvas.width=rect.width*dpr; canvas.height=rect.height*dpr;
  const ctx=canvas.getContext('2d'); ctx.scale(dpr,dpr);
  const W=rect.width, H=rect.height;
  ctx.clearRect(0,0,W,H);
  if(!data||data.length<2){
    ctx.fillStyle='#787B86'; ctx.font='13px IBM Plex Sans'; ctx.fillText('รอข้อมูลราคา...',20,H/2); return;
  }
  // normalise: รองรับทั้ง /api/prices (open/high/low/close/ts) และ /api/candles (o/h/l/c/t)
  const norm=d=>d.o!=null?{o:d.o,h:d.h,l:d.l,c:d.c,t:d.t,v:d.v||0}:{o:d.open,h:d.high,l:d.low,c:d.close,t:d.ts||d.t,v:d.volume||0};
  const nd=data.map(norm);
  const nAll=nd.length;
  const closes=nd.map(d=>d.c);

  // ── layout: price + (volume strip) + (RSI/ADX sub-panels) + time strip ──
  const PANE_H=88;              // ความสูง sub-pane เท่ากันทั้ง RSI/ADX → สัดส่วนสมดุล
  const PANE_MARGIN=13;         // padding แนวตั้ง 15% ของ pane กันเส้นชน/หลุดขอบกรอบ
  const timeStrip=18;           // แถบเวลาแยกจากกรอบล่างสุด ไม่เบียด ADX
  const subCount=(chartInd.rsi?1:0)+(chartInd.adx?1:0);
  const subH=subCount*PANE_H, volH=chartInd.vol?30:0, padL=8, padT=10;
  const priceH=H-subH-volH-timeStrip, plotH=priceH-padT;

  // ── หน้าต่าง + ช่องว่างขวา (future gap เหมือนโบรกเกอร์) ──
  const future=Math.max(3,Math.round(chartView.count*0.15));
  const realSlots=Math.max(5,chartView.count-future);
  let end=chartView.end; if(end<0||end>=nAll) end=nAll-1;
  let start=end-realSlots+1; if(start<0) start=0;
  const view=nd.slice(start,end+1);

  let min=Infinity,max=-Infinity;
  view.forEach(d=>{min=Math.min(min,d.l);max=Math.max(max,d.h);});
  const range=(max-min)||1; min-=range*0.06; max+=range*0.06;
  const dec=(max>1000||min>1000)?1:(max>100?2:(max>1?3:4));
  // ── EMA200 ล่าสุด + ระยะ snap S/R (ขนาด pip ตาม symbol) ──
  const emaArr=ema(closes,200);
  lastEma200=null;
  for(let i=nAll-1;i>=0;i--){ if(emaArr[i]!=null){lastEma200=emaArr[i];break;} }
  srSnapDist=Math.pow(10,-dec)*SR_SNAP_PIPS;
  ctx.font='9.5px IBM Plex Mono,monospace';
  const labelW=(max.toFixed(dec)).length*6.2+2;
  const padR=Math.max(50,labelW+14);
  const plotW=W-padL-padR;
  const step=plotW/(chartView.count-1), bw=Math.max(plotW/chartView.count*0.55,1);
  const pxForData=i=>padL+(i-start)*step;
  const py=v=>padT+(max-v)/(max-min)*plotH;
  const drawLine=(arr,color,width,yFn)=>{ ctx.strokeStyle=color; ctx.lineWidth=width||1.2; ctx.beginPath(); let started=false;
    for(let i=start;i<=end;i++){ const v=arr[i]; if(v==null) continue; const x=pxForData(i);
      const y=(yFn||py)(v);
      if(!started){ctx.moveTo(x,y);started=true;} else ctx.lineTo(x,y); }
    ctx.stroke(); };
  chartGeom={W,H,padL,padR,padT,plotH,start,end,step,min,max,dec,nd,pxForData,py};

  // ── drawPane: ตัววาด sub-pane มาตรฐาน (RSI/ADX) ──
  // ล็อคสเกล Y ที่ [min,max] + margin บน/ล่าง 15% → เส้นทุกเส้นมีระยะห่างจากขอบเสมอ
  const GRID_SOFT='rgba(162,178,212,.10)';   // gridline โปร่ง สบายตา (โทน #1e222d)
  const GRID_MAJ='rgba(162,178,212,.24)';    // gridline ระดับหลัก (50/40)
  function drawPane(o){
    const plotW=W-padL-padR;
    const pTop=o.oy+PANE_MARGIN, pBot=o.oy+PANE_H-PANE_MARGIN, plot=pBot-pTop;
    const yMap=v=>pBot-(v-o.min)/(o.max-o.min)*plot;   // mapper ที่มี padding ทั้ง 2 ด้าน
    // พื้นหลัง + กรอบ
    ctx.fillStyle='#10131A'; ctx.fillRect(padL,o.oy,plotW,PANE_H);
    ctx.strokeStyle='rgba(255,255,255,.06)'; ctx.strokeRect(padL,o.oy,plotW,PANE_H);
    // โซน (overbought/oversold) วาดก่อน gridline
    (o.zones||[]).forEach(z=>{
      const yA=yMap(Math.max(z.v0,z.v1)), yB=yMap(Math.min(z.v0,z.v1));
      ctx.fillStyle=z.color; ctx.fillRect(padL,yA,plotW,yB-yA);
    });
    // gridline + สเกลขวา (ไม่มี text overlay รกหน้าจออีกต่อไป)
    ctx.font='9.5px IBM Plex Mono,monospace';
    o.guides.forEach(g=>{
      const y=yMap(g.v);
      ctx.strokeStyle=g.major?GRID_MAJ:GRID_SOFT;
      ctx.setLineDash([3,3]); ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(W-padR,y); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle='#565B66'; ctx.textAlign='right'; ctx.fillText(g.v,W-6,y+3); ctx.textAlign='left';
    });
    // clip พื้นที่วาดจริง (กัน gradient/pill ล้นกรอบ)
    ctx.save(); ctx.beginPath(); ctx.rect(padL,pTop,plotW,plot); ctx.clip();
    // gradient fill ใต้เส้นชุดหลัก
    const fa=o.fill.arr, fv=fa[fa.length-1];
    if(fv!=null){
      const y0=yMap(fv);
      const grad=ctx.createLinearGradient(0,y0,0,pBot);
      grad.addColorStop(0,o.fill.color); grad.addColorStop(1,o.fill.color.replace(/[\d.]*\)$/,'0)'));
      ctx.fillStyle=grad;
      ctx.beginPath(); let started=false;
      for(let i=start;i<=end;i++){ const v=fa[i]; if(v==null) continue; const x=pxForData(i);
        if(!started){ctx.moveTo(x,yMap(v));started=true;} else ctx.lineTo(x,yMap(v)); }
      ctx.lineTo(pxForData(end),pBot); ctx.lineTo(pxForData(start),pBot); ctx.closePath(); ctx.fill();
    }
    // เส้น indicator (+DI/-DI/ADX หรือ RSI) — คงสีมาตรฐานเดิม
    o.lines.forEach(l=>drawLine(l.arr,l.color,l.width,yMap));
    ctx.restore();
    // ค่าล่าสุดเป็น pill ด้านขวา
    const pa=o.pill.arr, pv=pa[pa.length-1];
    if(pv!=null){
      const t=pv.toFixed(1), y=yMap(pv);
      ctx.font='bold 10px IBM Plex Mono,monospace';
      const tw=Math.min(ctx.measureText(t).width+12,padR-4);
      ctx.fillStyle=o.pill.color; ctx.beginPath(); ctx.roundRect(W-tw-2,y-8,tw,16,3); ctx.fill();
      ctx.fillStyle='#0A0C10'; ctx.textAlign='left'; ctx.fillText(t,W-tw+4,y+4); ctx.textAlign='left';
    }
  }

  // ── Grip: เส้นประที่ราคากลมๆ ──
  if(chartInd.grip){
    const rough=range/7, mag=Math.pow(10,Math.floor(Math.log10(rough)));
    const nv=rough/mag, gstep=(nv<1.5?1:nv<3.5?2:nv<7.5?5:10)*mag;
    ctx.setLineDash([2,4]); ctx.strokeStyle='rgba(255,255,255,.07)'; ctx.lineWidth=1;
    for(let v=Math.ceil(min/gstep)*gstep; v<=max; v+=gstep){
      ctx.beginPath(); ctx.moveTo(padL,py(v)); ctx.lineTo(W-padR,py(v)); ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  // ── BB (20,2) ──
  if(chartInd.bb){
    const bb=bollinger(closes,20,2);
    ctx.strokeStyle='rgba(140,160,200,.6)'; ctx.lineWidth=1; ctx.setLineDash([3,3]);
    [bb.up,bb.mid,bb.low].forEach(arr=>{ ctx.beginPath(); let st=false;
      for(let i=start;i<=end;i++){ const v=arr[i]; if(v==null) continue; const x=pxForData(i);
        if(!st){ctx.moveTo(x,py(v));st=true;} else ctx.lineTo(x,py(v)); }
      ctx.stroke(); });
    ctx.setLineDash([]);
  }

  // ── EMA 50/100/200 (แทน EMA20 เดิม → EMA100) ──
  if(chartInd.ema){
    drawLine(ema(closes,200),'rgba(243,168,70,.95)',1.6);
    drawLine(ema(closes,100),'rgba(41,98,255,.9)',1.2);
    drawLine(ema(closes,50),'rgba(41,98,255,.9)',1.2);
  }

  // ── SMA5 ──
  if(chartInd.sma5) drawLine(sma(closes,5),'rgba(232,238,251,.9)',1);

  // ── Fractal: จุดยอด (ยอดสูง/ต่ำล่าสุด → สร้างเส้น S/R อัตโนมัติใน srLevels) ──
  if(chartInd.fractal){
    const fr=fractal(nd,7,7).filter(p=>p.i>=start&&p.i<=end);
    const lastH=fr.filter(p=>p.t==='H').pop(), lastL=fr.filter(p=>p.t==='L').pop();
    upsertSr('fH', lastH?lastH.v:null, 'R', false);
    upsertSr('fL', lastL?lastL.v:null, 'S', false);
    fr.forEach(p=>{
      const x=pxForData(p.i), y=py(p.v);
      if(p.t==='H'){
        ctx.fillStyle='#EF5350';
        ctx.beginPath(); ctx.moveTo(x,y-7); ctx.lineTo(x-4,y); ctx.lineTo(x+4,y); ctx.closePath(); ctx.fill();
      } else {
        ctx.fillStyle='#26A69A';
        ctx.beginPath(); ctx.moveTo(x,y+7); ctx.lineTo(x-4,y); ctx.lineTo(x+4,y); ctx.closePath(); ctx.fill();
      }
    });
  }

  // ── S/R lines: interactive (ลากปรับระดับ · เพิ่มเองได้ · snap/highlight โซน EMA200) ──
  const srRects=[];   // ช่วง y ที่ label ครอบครอง → กันชน label ขวากับ grid/price tag
  const srLabelY=y=>{
    for(let off=0;off<=5;off++){ const yy=y-off*17;
      if(yy-9>=padT&&!srRects.some(r=>yy-8<r[1]&&yy+8>r[0])){ srRects.push([yy-8,yy+8]); return yy; } }
    for(let off=1;off<=5;off++){ const yy=y+off*17;
      if(yy+9<=padT+plotH&&!srRects.some(r=>yy-8<r[1]&&yy+8>r[0])){ srRects.push([yy-8,yy+8]); return yy; } }
    srRects.push([y-8,y+8]); return y;
  };
  if(srLevels.length){
    ctx.font='bold 9px IBM Plex Mono,monospace';
    srLevels.forEach(lv=>{
      const y=py(lv.price);
      if(y<padT-10||y>padT+plotH+10) return;
      const nearEma=lastEma200!=null&&Math.abs(lv.price-lastEma200)<=srSnapDist;
      const dragging=srDrag&&srDrag.id===lv.id;
      const col=nearEma?'#FF9800':(lv.type==='R'?'#EF5350':'#26A69A');
      const alpha=(nearEma||lv.manual||dragging)?'':'bb';
      ctx.strokeStyle=col+alpha; ctx.lineWidth=dragging?1.6:1.1;
      ctx.setLineDash(lv.manual||dragging?[6,4]:[2,4]);
      ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(W-padR,y); ctx.stroke();
      ctx.setLineDash([]);
      // จุดจับลาก (ขวา)
      ctx.fillStyle=col+alpha; ctx.beginPath(); ctx.arc(W-padR-5,y,3,0,7); ctx.fill();
      // label ราคา (ขวา) — จัดไม่ให้ซ้อนกับ label อื่น/price tag
      const ty=srLabelY(y);
      const txt=(lv.type==='R'?'R ':'S ')+lv.price.toFixed(dec);
      const tw=Math.min(ctx.measureText(txt).width+8,padR-4);
      ctx.fillStyle=col+(alpha||''); ctx.beginPath(); ctx.roundRect(W-padR-tw-2,ty-7,tw,14,3); ctx.fill();
      ctx.fillStyle='#0A0C10'; ctx.textAlign='left'; ctx.fillText(txt,W-padR-tw+2,ty+4); ctx.textAlign='left';
      // เตือน: อยู่ในโซน EMA200 (ห่างไม่เกิน 5 pips)
      if(nearEma){
        ctx.strokeStyle='rgba(247,184,71,.5)'; ctx.lineWidth=1;
        ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(W-padR,y); ctx.stroke();
        ctx.fillStyle='#FF9800'; ctx.font='bold 8.5px IBM Plex Mono,monospace';
        const btxt='EMA200';
        const btw=ctx.measureText(btxt).width+8;
        ctx.beginPath(); ctx.roundRect(padL+2,Math.max(y-13,padT+2),btw,12,3); ctx.fill();
        ctx.fillStyle='#0A0C10'; ctx.textAlign='left'; ctx.fillText(btxt,padL+6,Math.max(y-13,padT+2)+9); ctx.textAlign='left';
        ctx.font='bold 9px IBM Plex Mono,monospace';
      }
    });
  }

  // ── grid + price labels (right axis) — ข้าม label ที่ชนกับ label S/R ──
  ctx.strokeStyle='#1C2029'; ctx.fillStyle='#565B66'; ctx.font='9.5px IBM Plex Mono,monospace';
  const GRID=5;
  for(let i=0;i<=GRID;i++){
    const y=padT+plotH*i/GRID;
    ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(W-padR,y); ctx.stroke();
    if(srRects.some(r=>y-8<r[1]&&y+8>r[0])) continue;
    ctx.textAlign='right'; ctx.fillText((max-(max-min)*i/GRID).toFixed(dec),W-6,y+3);
  }
  ctx.textAlign='left';

  // ── candles ──
  view.forEach((d,i)=>{
    const x=pxForData(i+start), up=d.c>=d.o;
    ctx.strokeStyle=up?'#26A69A':'#EF5350'; ctx.fillStyle=up?'#26A69A':'#EF5350';
    ctx.beginPath(); ctx.moveTo(x,py(d.h)); ctx.lineTo(x,py(d.l)); ctx.stroke();
    const yO=py(d.o),yC=py(d.c),top=Math.min(yO,yC),hgt=Math.max(Math.abs(yO-yC),1);
    ctx.fillRect(x-bw/2,top,bw,hgt);
  });

  // ── Signal markers: แสดงจุดเข้าชัดเจน พร้อม vertical line + entry price line ──
  if(window._signalMarkers){
    const tsMap={};
    view.forEach((d,i)=>{ tsMap[d.t]=i; });

    // วาด markers ทีหลังสุด (ทับกราฟทั้งหมด)
    window._signalMarkers.forEach(m=>{
      if(!m.ts||!m.price||!m.direction) return;
      let idx=-1;
      for(const [t,i] of Object.entries(tsMap)){
        if(Math.abs(new Date(t)-new Date(m.ts))<300000){ idx=parseInt(i); break; }
      }
      if(idx<0) return;
      const dataIdx=idx+start;
      const x=pxForData(dataIdx), y=py(m.price);
      const candle=view[idx];
      if(!candle) return;
      const candleBottom=py(candle.l), candleTop=py(candle.h);
      const isCall=m.direction==='CALL';

      // ผลลัพธ์
      const isWin=m.result==='WIN'||m.result==='TP1'||m.result==='TP2';
      const isLose=m.result==='LOSE'||m.result==='SL';
      const isOpen=m.result==='PENDING';

      // สีตามผล — ทุกระบบใช้สีเดียวกัน
      const color=isWin?'#26A69A':isLose?'#EF5350':'#FF9800';

      // ชื่อระบบ
      const sysLabel=m.type==='ML'?'ML':m.importance===1?'IMP1':m.importance===2?'IMP2':'RBF';

      // ── 1. Vertical line จาก marker ลงมาที่แท่งเทียน ──
      const vLineTop=isCall?y+14:candleTop-4;
      const vLineBot=isCall?candleBottom+4:y-14;
      ctx.strokeStyle=color; ctx.lineWidth=1.5; ctx.globalAlpha=0.5;
      ctx.setLineDash([2,2]);
      ctx.beginPath(); ctx.moveTo(x,vLineTop); ctx.lineTo(x,vLineBot); ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha=1;

      // ── 2. Entry price horizontal line ──
      ctx.strokeStyle=color; ctx.lineWidth=1; ctx.globalAlpha=0.35;
      ctx.setLineDash([6,3]);
      ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(W-padR,y); ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha=1;

      // ── 3. Triangle ใหญ่ ──
      const triH=10, triW=7;
      ctx.fillStyle=color;
      if(isCall){
        // CALL = ขีลูกศรขึ้น วางใต้แท่ง
        const ty=candleBottom+6;
        ctx.beginPath(); ctx.moveTo(x,ty+triH); ctx.lineTo(x-triW,ty); ctx.lineTo(x+triW,ty); ctx.closePath(); ctx.fill();
        // ลูกศรเส้น
        ctx.strokeStyle=color; ctx.lineWidth=2;
        ctx.beginPath(); ctx.moveTo(x,ty+triH); ctx.lineTo(x,ty-4); ctx.stroke();
      } else {
        // PUT = ลูกศรชี้ลง วางเหนือแท่ง
        const ty=candleTop-6;
        ctx.beginPath(); ctx.moveTo(x,ty-triH); ctx.lineTo(x-triW,ty); ctx.lineTo(x+triW,ty); ctx.closePath(); ctx.fill();
        ctx.strokeStyle=color; ctx.lineWidth=2;
        ctx.beginPath(); ctx.moveTo(x,ty-triH); ctx.lineTo(x,ty+4); ctx.stroke();
      }

      // ── 4. ป้ายข้อมูล: [DIR] @price (SYS) [RESULT] ──
      const dec2=m.price>=100?2:m.price>=10?1:3;
      const priceStr=m.price.toFixed(dec2);
      const dirText=isCall?'▲ CALL':'▼ PUT';
      const resultText=isWin?'WIN':isLose?'LOSE':'OPEN';
      const fullLabel=dirText+' @'+priceStr+' ['+sysLabel+'] '+resultText;

      ctx.font='bold 9px IBM Plex Mono,monospace'; ctx.textAlign='center';
      const lw=ctx.measureText(fullLabel).width+10;
      const ly=isCall?candleBottom+24:candleTop-24;
      const lyClamped=Math.min(Math.max(ly,20),H-20);

      // background pill
      ctx.fillStyle='rgba(10,12,16,.88)';
      ctx.beginPath(); ctx.roundRect(x-lw/2,lyClamped-8,lw,16,4); ctx.fill();
      ctx.strokeStyle=color; ctx.lineWidth=1;
      ctx.beginPath(); ctx.roundRect(x-lw/2,lyClamped-8,lw,16,4); ctx.stroke();

      // text — split color
      const dirColor=isCall?'#26A69A':'#EF5350';
      const parts=[{t:dirText,c:dirColor},{t:' @'+priceStr,c:'#EDEFF3'},{t:' ['+sysLabel+']',c:'#838B9C'},{t:' '+resultText,c:color}];
      let tx=x-lw/2+5;
      ctx.textAlign='left'; ctx.font='bold 9px IBM Plex Mono,monospace';
      parts.forEach(p=>{
        ctx.fillStyle=p.c; ctx.fillText(p.t,tx,lyClamped+3); tx+=ctx.measureText(p.t).width;
      });
      ctx.textAlign='center';
    });

    // ── CFD SL/TP levels (วาดทีหลัง ทับทุกอย่าง) ──
    window._signalMarkers.forEach(m=>{
      if(!m.cfd||!m.ts||!m.price||!m.direction) return;
      let idx=-1;
      for(const [t,i] of Object.entries(tsMap)){
        if(Math.abs(new Date(t)-new Date(m.ts))<300000){ idx=parseInt(i); break; }
      }
      if(idx<0) return;
      const x=pxForData(idx+start);
      const lineLen=Math.min(50,(W-padR-padL)/4);
      const xEnd=x+lineLen;
      ctx.globalAlpha=0.7;
      if(m.cfd.sl){
        const ySL=py(m.cfd.sl);
        ctx.strokeStyle='#EF5350'; ctx.lineWidth=1; ctx.setLineDash([3,3]);
        ctx.beginPath(); ctx.moveTo(padL,ySL); ctx.lineTo(xEnd,ySL); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle='rgba(10,12,16,.85)'; ctx.font='bold 8px IBM Plex Mono,monospace';
        const slText='SL '+m.cfd.sl.toFixed(2);
        const slW=ctx.measureText(slText).width+6;
        ctx.fillRect(xEnd+3,ySL-7,slW,12);
        ctx.fillStyle='#EF5350'; ctx.fillText(slText,xEnd+6,ySL+3);
      }
      if(m.cfd.tp1){
        const yTP1=py(m.cfd.tp1);
        ctx.strokeStyle='#FF9800'; ctx.lineWidth=1; ctx.setLineDash([3,3]);
        ctx.beginPath(); ctx.moveTo(padL,yTP1); ctx.lineTo(xEnd,yTP1); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle='rgba(10,12,16,.85)'; ctx.font='bold 8px IBM Plex Mono,monospace';
        const tp1Text='TP1 '+m.cfd.tp1.toFixed(2);
        const tp1W=ctx.measureText(tp1Text).width+6;
        ctx.fillRect(xEnd+3,yTP1-7,tp1W,12);
        ctx.fillStyle='#FF9800'; ctx.fillText(tp1Text,xEnd+6,yTP1+3);
      }
      if(m.cfd.tp2){
        const yTP2=py(m.cfd.tp2);
        ctx.strokeStyle='#26A69A'; ctx.lineWidth=1; ctx.setLineDash([3,3]);
        ctx.beginPath(); ctx.moveTo(padL,yTP2); ctx.lineTo(xEnd,yTP2); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle='rgba(10,12,16,.85)'; ctx.font='bold 8px IBM Plex Mono,monospace';
        const tp2Text='TP2 '+m.cfd.tp2.toFixed(2);
        const tp2W=ctx.measureText(tp2Text).width+6;
        ctx.fillRect(xEnd+3,yTP2-7,tp2W,12);
        ctx.fillStyle='#26A69A'; ctx.fillText(tp2Text,xEnd+6,yTP2+3);
      }
      ctx.globalAlpha=1;
    });
  }

  // ── last price: เส้น + tag pill ──
  const lp=view[view.length-1].c, lc=lp>=view[view.length-1].o?'#26A69A':'#EF5350';
  ctx.strokeStyle=lc; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(padL,py(lp)); ctx.lineTo(W-padR,py(lp)); ctx.stroke(); ctx.setLineDash([]);
  const tag=lp.toFixed(dec);
  ctx.font='bold 10px IBM Plex Mono,monospace';
  const tw=Math.min(ctx.measureText(tag).width+12,padR-4);
  let ty=Math.min(Math.max(py(lp)-8,6),H-24);
  // กันชนกับ label S/R ฝั่งขวา → ขยับขึ้นไม่ให้ซ้อน
  if(srRects.length&&srRects.some(r=>ty-8<r[1]&&ty+16>r[0])) ty=Math.min(Math.max(py(lp)-22,6),H-24);
  ctx.fillStyle=lc; ctx.beginPath(); ctx.roundRect(W-tw-2,ty,tw,16,3); ctx.fill();
  ctx.fillStyle='#0A0C10'; ctx.textAlign='left'; ctx.fillText(tag,W-tw+4,ty+12); ctx.textAlign='left';

  // ── volume strip ──
  let volTop=priceH;
  if(chartInd.vol){
    const vh=volH-4, vmax=Math.max(...view.map(d=>d.v),1);
    ctx.fillStyle='#10131A'; ctx.fillRect(0,volTop,W,volH);
    ctx.fillStyle='#565B66'; ctx.font='9.5px IBM Plex Mono,monospace'; ctx.textAlign='left';
    ctx.fillText('VOL',padL+2,volTop+10);
    view.forEach((d,i)=>{
      const x=pxForData(i+start), hh=d.v/vmax*(vh-6);
      ctx.fillStyle=(d.c>=d.o)?'rgba(38,166,154,.25)':'rgba(239,83,80,.25)';
      ctx.fillRect(x-bw/2,volTop+vh-2-hh,bw,hh);
    });
    volTop+=volH;
  }

  // ── RSI/ADX sub-panes (ใช้ drawPane ร่วมกัน: สเกลล็อค + margin กันเส้นหลุดขอบ) ──
  let oy=volTop;
  if(chartInd.rsi){
    const rv=rsi(closes,14);
    drawPane({
      oy,
      min:0, max:100,                       // สเกล RSI คงที่ 0–100
      guides:[{v:0},{v:30},{v:50,major:true},{v:70},{v:100}],
      zones:[{v0:70,v1:100,color:'rgba(239,83,80,.08)'},
             {v0:0,v1:30,color:'rgba(38,166,154,.08)'}],
      fill:{arr:rv, color:'rgba(247,184,71,.30)'},
      lines:[{arr:rv, color:'#FF9800', width:1.2}],
      pill:{arr:rv, color:'#FF9800'}
    });
    oy+=PANE_H;
  }
  if(chartInd.adx){
    const aa=adx(nd.map(d=>d.h),nd.map(d=>d.l),closes,14);
    // ล็อคสเกล ADX: ขั้นต่ำ 0–80, ขยายปัดขึ้นเป็นสิบถ้าข้อมูลจริงเกิน → เส้นไม่หลุดขอบบน
    let aMax=0;
    for(let i=start;i<=end;i++) aMax=Math.max(aMax,aa.pdi[i]||0,aa.ndi[i]||0,aa.adx[i]||0);
    aMax=Math.max(80,Math.ceil(aMax/10)*10);
    drawPane({
      oy,
      min:0, max:aMax,
      guides:[{v:0},{v:20},{v:40,major:true},{v:60},{v:80}],
      zones:[{v0:0,v1:20,color:'rgba(38,166,154,.07)'}],
      fill:{arr:aa.adx, color:'rgba(247,184,71,.22)'},
      lines:[{arr:aa.pdi, color:'rgba(38,166,154,.75)', width:1.2},
             {arr:aa.ndi, color:'rgba(239,83,80,.75)', width:1.2},
             {arr:aa.adx, color:'#FF9800', width:1.2}],
      pill:{arr:aa.adx, color:'#FF9800'}
    });
  }

  // ── time strip: แยกจากกรอบล่างสุดด้วยเส้นคั่น ไม่เบียดขอบ ADX ──
  ctx.strokeStyle='rgba(255,255,255,.06)';
  ctx.beginPath(); ctx.moveTo(padL,H-timeStrip); ctx.lineTo(W-padR,H-timeStrip); ctx.stroke();
  ctx.fillStyle='#565B66'; ctx.font='9.5px IBM Plex Mono,monospace';
  ctx.textAlign='left';
  ctx.fillText(view[0].t?fmtHM(view[0].t):'',padL,H-6);
  ctx.fillText(view[view.length-1].t?fmtHM(view[view.length-1].t):'',Math.min(pxForData(end),W-padR-70),H-6);
  ctx.textAlign='right';
  ctx.fillStyle='rgba(74,87,117,.8)';
  ctx.fillText(realSlots>=nAll?'ALL':realSlots+' แท่ง',W-6,H-6);
  ctx.textAlign='left';

  // ── crosshair (เหมือน TradingView: กากบาท + OHLC box + ไฮไลต์แท่ง) ──
  let legendIdx=nd.length-1;
  if(crosshair){
    const cx=crosshair.x, cy=crosshair.y;
    if(cx>=padL&&cx<=W-padR&&cy>=padT&&cy<=padT+plotH){
      const cbar=Math.round((cx-padL)/step)+start;
      const bi=Math.max(start,Math.min(end,cbar));
      legendIdx=bi;
      const d=nd[bi];
      if(d){
        const bx=pxForData(bi), by=py(d.c);
        // ไฮไลต์แท่งที่ hover
        ctx.fillStyle='rgba(41,98,255,.10)';
        ctx.fillRect(bx-bw/2,padT,bw,plotH);
        // เส้นกากบาท
        ctx.strokeStyle='rgba(232,238,251,.35)'; ctx.lineWidth=1;
        ctx.setLineDash([3,3]);
        ctx.beginPath(); ctx.moveTo(cx,padT); ctx.lineTo(cx,padT+plotH); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(padL,cy); ctx.lineTo(W-padR,cy); ctx.stroke();
        ctx.setLineDash([]);
        // ราคาที่ hover: pill ฝั่งขวา
        const hp=max-(cy-padT)/plotH*(max-min);
        ctx.font='bold 10px IBM Plex Mono,monospace';
        const ht=hp.toFixed(dec);
        const htw=Math.min(ctx.measureText(ht).width+12,padR-4);
        ctx.fillStyle='rgba(26,36,64,.9)'; ctx.beginPath(); ctx.roundRect(W-htw-2,cy-8,htw,16,3); ctx.fill();
        ctx.fillStyle='#EDEFF3'; ctx.textAlign='left'; ctx.fillText(ht,W-htw+4,cy+4); ctx.textAlign='left';
        // เวลาที่ hover: pill ฝั่งล่าง
        const tt=d.t?fmtHM(d.t):'';
        if(tt){
          ctx.font='bold 9px IBM Plex Mono,monospace';
          const ttw=ctx.measureText(tt).width+12;
          const tx=Math.min(Math.max(bx-ttw/2,padL),W-padR-ttw);
          ctx.fillStyle='rgba(26,36,64,.9)'; ctx.beginPath(); ctx.roundRect(tx,H-18,ttw,14,3); ctx.fill();
          ctx.fillStyle='#EDEFF3'; ctx.textAlign='left'; ctx.fillText(tt,tx+6,H-8); ctx.textAlign='left';
        }
        // OHLC box (มุมซ้ายบน เหมือน TradingView)
        const bx2=padL+8, by2=padT+8;
        ctx.fillStyle='rgba(10,15,26,.82)';
        ctx.beginPath(); ctx.roundRect(bx2,by2,88,74,6); ctx.fill();
        ctx.strokeStyle='rgba(38,50,89,.8)'; ctx.strokeRect(bx2+.5,by2+.5,87,73);
        ctx.font='bold 9px IBM Plex Mono,monospace';
        ctx.fillStyle='#838B9C'; ctx.textAlign='left';
        ctx.fillText(d.t?fmtTime(d.t):'',bx2+7,by2+12);
        const up=d.c>=d.o;
        [['O',d.o,up],['H',d.h,up],['L',d.l,up],['C',d.c,up]].forEach((r,i)=>{
          const yy=by2+28+i*11;
          ctx.fillStyle='#838B9C'; ctx.fillText(r[0],bx2+7,yy);
          ctx.fillStyle=r[2]?'#26A69A':'#EF5350';
          ctx.fillText(r[1].toFixed(dec),bx2+26,yy);
        });
      }
    }
  }

  // ── legend overlay: ค่าล่าสุดของ indicator (อัปเดตทุก redraw) ──
  updateLegendOverlay(nd, legendIdx);
  }
}
function updateLegendOverlay(nd, idx){
  const bar=document.getElementById('chartLegendBar'); if(!bar) return;
  const closes=nd.map(d=>d.c);
  const at=Math.max(0,Math.min((idx==null?nd.length-1:idx),nd.length-1));
  const d=nd[at];
  const dec=(nd[nd.length-1]&&nd[nd.length-1].c>1000)?1:(nd[nd.length-1]&&nd[nd.length-1].c>100?2:3);
  const f=v=>v==null||isNaN(v)?'–':v.toFixed(dec);
  // OHLC (ไม่บังแท่งเทียน — อยู่คนละบรรทัด)
  const ohlc=document.getElementById('lbOhlc');
  if(ohlc&&d){
    const up=d.c>=d.o;
    ohlc.innerHTML=
      `<span>O <b>${f(d.o)}</b></span>`+
      `<span>H <b>${f(d.h)}</b></span>`+
      `<span>L <b>${f(d.l)}</b></span>`+
      `<span class="${up?'up':'dn'}">C <b>${f(d.c)}</b></span>`+
      `<span class="muted">Δ ${f(d.c-d.o)}</span>`;
  }
  // ค่าล่าสุดของ indicator (คลิกที่ chip = สลับปิด/เปิด เหมือนเดิม)
  const chips=[];
  const chip=(key,label,color,val,extra)=>{
    if(!chartInd[key]) return;
    chips.push(`<span class="lo-chip" data-ind="${key}" title="คลิกปิด/เปิด">`+
      `<span class="sw" style="background:${color}"></span>`+
      `<span class="lbl">${label}</span> <b>${f(val)}</b>${extra||''}</span>`);
  };
  if(chartInd.ema){
    const e50=ema(closes,50)[at], e100=ema(closes,100)[at], e200=ema(closes,200)[at];
    chip('ema','EMA50','#38e1c4',e50);
    chip('ema','EMA100','#a78bfa',e100);
    chip('ema','EMA200','#f3a846',e200);
  }
  if(chartInd.sma5){ const s5=sma(closes,5)[at]; chip('sma5','SMA5','#EDEFF3',s5); }
  if(chartInd.bb){ const b=bollinger(closes,20,2); chip('bb','BB', '#8ca0c8', b.up[at], ' / '+f(b.low[at])); }
  if(chartInd.rsi){ const rv=rsi(closes,14)[at]; chip('rsi','RSI14','#FF9800',rv); }
  if(chartInd.adx){ const a=adx(nd.map(d=>d.h),nd.map(d=>d.l),closes,14); chip('adx','ADX','#FF9800',a.adx[at], ' +'+f(a.pdi[at])+' −'+f(a.ndi[at])); }
  document.getElementById('lbValues').innerHTML=chips.join('');
}
function zoomChartAt(factor, frac){
  if(!lastCandles.length) return;
  const nAll=lastCandles.length;
  const future=Math.max(3,Math.round(chartView.count*0.15));
  const realSlots=Math.max(5,chartView.count-future);
  let end=(chartView.end<0||chartView.end>=nAll)?nAll-1:chartView.end;
  const start=Math.max(0,end-realSlots+1);
  // แท่งที่อยู่ใต้ cursor: map ผ่าน px เดียวกับ pxForData (ใช้ count-1)
  const anchor=Math.min(end,start+Math.round(frac*(chartView.count-1)));
  const newCount=Math.min(300,Math.max(30,Math.round(chartView.count*factor)));
  const newFuture=Math.max(3,Math.round(newCount*0.15));
  const newReal=Math.max(5,newCount-newFuture);
  // ยึด anchor ไว้ที่ pixel เดิม: ใช้ (newCount-1) ให้ตรง pxForData → cursor นิ่ง ไม่ไถล
  let newStart=Math.round(anchor-frac*(newCount-1));
  newStart=Math.max(0,Math.min(newStart,nAll-newCount));
  chartView.count=newCount;
  chartView.end=newStart+newReal-1;
  drawCandles(document.getElementById('candleChart'),lastCandles);
}
function panChart(deltaIdx){
  if(!lastCandles.length) return;
  const nAll=lastCandles.length;
  const future=Math.max(3,Math.round(chartView.count*0.15));
  const realSlots=Math.max(5,chartView.count-future);
  let end=(chartView.end<0||chartView.end>=nAll)?nAll-1:chartView.end;
  end=Math.min(nAll-1,Math.max(realSlots-1,end+deltaIdx));
  chartView.end=end;
  drawCandles(document.getElementById('candleChart'),lastCandles);
}
function resetChartView(){
  chartView.count=300; chartView.end=-1;
  if(lastCandles.length) drawCandles(document.getElementById('candleChart'),lastCandles);
}

/* ═══════ INTERACTIVE SUPPORT/RESISTANCE ═══════ */
const SR_SNAP_PIPS=5;   // ลาก S/R เข้าใกล้ EMA200 ไม่เกินกี่ pips → snap + เตือน
let srLevels=[];        // [{id, price, type:'R'|'S', manual:boolean}]
let srPinned={};        // auto-line ที่ user ลากแล้ว → fractal ไม่เขียนทับ
let srSeq=0;            // ตัวนับ id สำหรับเส้นที่สร้างเอง
let srDrag=null;        // {id} ขณะลากเส้น
let srSnapDist=0;       // = SR_SNAP_PIPS * 10^-dec (ขนาด pip ตาม symbol)
let lastEma200=null;    // EMA200 ล่าสุด ใช้ตอนลาก snap

function upsertSr(id, price, type, manual){
  const lv=srLevels.find(l=>l.id===id);
  if(lv){ if(!srPinned[id]&&price!=null) lv.price=price; }
  else if(price!=null) srLevels.push({id, price, type, manual});
}
function hitSrAt(x,y){
  if(!chartGeom||!srLevels.length) return null;
  const {padL,padR,padT,plotH,py,W}=chartGeom;
  if(x<padL||x>W-padR||y<padT||y>padT+plotH) return null;
  let best=null,bd=6;
  for(const lv of srLevels){
    const d=Math.abs(y-py(lv.price));
    if(d<bd){bd=d;best=lv;}
  }
  return best;
}
function addSrLine(type){
  if(!lastCandles.length) return;
  const last=lastCandles[lastCandles.length-1];
  srLevels.push({id:'m'+(++srSeq), price:last.c, type, manual:true});
  drawCandles(document.getElementById('candleChart'),lastCandles);
}

