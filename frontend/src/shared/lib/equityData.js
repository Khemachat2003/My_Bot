// แปลงข้อมูล equity (journal + CFD paper) เป็นจุดกราฟ
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1996–2027 แบบ move-only
// TODO: ย้ายไป backend — ประกอบ equity curve (capital + equity*stake, cumulative pnl ของ CFD, base 5000) ฝั่งหน้าเว็บ

function _eqTS(t){
  if(t==null) return 0;
  if(typeof t==='number') return Math.floor(t);
  const s=String(t);
  const a=Math.floor(new Date(s.replace(' ','T')+'Z').getTime()/1000);
  return (Number.isFinite(a)&&a>0)?a:Math.floor(new Date(s.replace(' ','T')).getTime()/1000);
}

function _uniqueTimesAsc(pts){
  // lightweight-charts ต้องการแกนเวลาเป็นลำดับเพิ่มขึ้นแบบไม่ซ้ำ
  // เทรดที่จบในวินาทีเดียวกัน (burst) → time ซ้ำกัน → กราฟ crash "Value is null"
  let last=0;
  return pts.map(p=>{ const t=p.time; const time=t>last?t:last+1; last=time; return {time, value:p.value}; });
}

function _buildEqData(opt, cfd){
  const optPts=_uniqueTimesAsc(((opt&&opt.points)||[]).map(p=>({
    time:_eqTS(p.t),
    value:Math.round((opt.capital||0)+((p.equity||0)*(opt.stake||1))),
  })).filter(d=>d.time>0));
  let cum=0;
  const cfdPts=_uniqueTimesAsc(((cfd&&cfd.points)||[]).map(p=>{
    cum+=(p.pnl||0);
    return {time:_eqTS(p.exit_time||p.t), value:Math.round((cfd.base||0)+cum)};
  }).filter(d=>d.time>0));
  const optN=optPts.length, cfdN=cfdPts.length;
  const optCapitalBase=(opt&&opt.capital)||0, cfdBase=(cfd&&cfd.base)||0;
  const cfdPnl=cfdN?cfdPts[cfdPts.length-1].value-cfdBase:0;
  const optPnl=optN?optPts[optPts.length-1].value-optCapitalBase:0;
  return {optPts, cfdPts, optN, cfdN, optPnl, cfdPnl, optCapitalBase, cfdBase};
}

// ═══ C-18: ตัดจุด equity ตามช่วงเวลา (วันนี้ / 7d / 30d / 90d / ทั้งหมด) ═══
// คืน {pts, carry, n} —
//   pts   = จุดในช่วง + จุดสังเคราะห์ 1 จุดที่ fromTs ยกค่าทุน "ตอนเริ่มช่วง" (carry-in)
//           → เส้นเริ่มวิ่งจากฐานจริง ไม่ลอย ๆ กลางอากาศ (และ baseline series ตั้ง base ที่ carry
//           → fill เขียว/แดง = บวก/ลบ "ตั้งแต่ต้นช่วง" ตาม pro investor ดู)
//   carry = ทุนยกเข้า (null ถ้าไม่มีข้อมูลก่อนช่วง — ใช้ base เดิมแทน)
//   n     = จำนวนเทรดจริงในช่วง (ไม่นับจุดสังเคราะห์)
// กัน time ซ้ำ: จุดสังเคราะห์ใส่เฉพาะเมื่อจุดแรกในช่วงเริ่มหลัง fromTs จริง ๆ
function _eqSlice(pts, fromTs){
  if(!pts||!pts.length) return {pts:[], carry:null, n:0};
  if(fromTs==null) return {pts, carry:null, n:pts.length};
  let i=pts.findIndex(p=>p.time>=fromTs);
  if(i===-1) return {pts:[], carry:pts[pts.length-1].value, n:0};
  const carry=i>0?pts[i-1].value:null;
  const sliced=pts.slice(i);
  const prepend=carry!=null&&sliced.length>0&&sliced[0].time>fromTs;
  return {pts:prepend?[{time:fromTs,value:carry},...sliced]:sliced, carry, n:sliced.length};
}
// ขอบเขตเวลาของแต่ละช่วง (unix วินาที) — 'today' = เที่ยงคืนท้องถิ่นของวันนี้
function _eqRangeStart(range){
  if(range==='today'){
    const d=new Date(); d.setHours(0,0,0,0);
    return Math.floor(d.getTime()/1000);
  }
  if(range==='7d') return Math.floor(Date.now()/1000)-7*86400;
  if(range==='30d') return Math.floor(Date.now()/1000)-30*86400;
  if(range==='90d') return Math.floor(Date.now()/1000)-90*86400;
  return null; // 'all'
}


export { _buildEqData, _eqRangeStart, _eqSlice };
