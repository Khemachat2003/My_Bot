# Bug Fix Brief: Loading flash / ปุ่มไม่ทำงาน / Indicator ทับกัน / Fractal สีเดียวกัน

ตรวจโค้ดจริงในไฟล์ `index.html` แล้ว เจอสาเหตุที่ยืนยันได้ชัดเจนของทุกข้อ พร้อมโค้ดแก้ไขที่ก็อปวางแทนที่ได้เลย

---

## ข้อ 1: กราฟติดหน้า "กำลังโหลด" ถี่จนขัดตา

### สาเหตุ (ยืนยันจากโค้ด)
`refreshPrice()` ถูกเรียกทุก 5 วินาทีผ่าน `setInterval(refreshAll, REFRESH_MS)` (บรรทัด `const REFRESH_MS = 5000`) และ **ทุกครั้งที่เรียก ไม่ว่าจะเป็นการรีเฟรชพื้นหลังเงียบๆ หรือผู้ใช้กดเปลี่ยน TF เอง โค้ดจะ toggle class `.loading` ที่ทำให้จอมืดลง + ขึ้นข้อความ "กำลังโหลด…" ทุกครั้งเหมือนกันหมด** ทำให้จอกระพริบทุก 5 วินาทีตลอดเวลาที่เปิดหน้าไว้

### วิธีแก้
แสดง loading overlay **เฉพาะตอนผู้ใช้กดเปลี่ยน TF/symbol เอง** เท่านั้น ไม่ใช่ตอน auto-poll เบื้องหลัง:

```js
// เดิม: async function refreshPrice(){ ... }
// ใหม่: เพิ่มพารามิเตอร์ showLoading (default false เพื่อไม่ให้ auto-poll แสดง)
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
    if(showLoading && wrap) wrap.classList.add('loading');   // ← เงื่อนไขใหม่
    const [[prices,markers]]=await Promise.all([
      Promise.all([
        (async()=>{
          let p=await fetchJSON('/api/candles?tf='+tf+'&count=300&symbol='+encodeURIComponent(sym));
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
    // ...ส่วนที่เหลือคงเดิมทั้งหมด...
  }catch(e){ console.error(e); }
}
```

แล้วแก้จุดที่เรียก `refreshPrice()` ให้ผ่าน `true` เฉพาะตอนเป็น user action:

```js
// ปุ่มเปลี่ยน TF, dropdown เปลี่ยน symbol → ใส่ true
document.getElementById('tfGroup')?.addEventListener('click',e=>{
  const btn=e.target.closest('.tf-btn'); if(!btn) return;
  document.querySelectorAll('#tfGroup .tf-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  refreshPrice(true);   // ← user-triggered
});
document.getElementById('chartSymbol')?.addEventListener('change',()=>refreshPrice(true)); // ← user-triggered

// ส่วนของ setInterval(refreshAll, REFRESH_MS) ที่เรียก refreshPrice() เฉยๆ ไม่ต้องแก้ (default false อยู่แล้ว)
```

ผลลัพธ์: การรีเฟรชอัตโนมัติเบื้องหลังจะอัปเดตข้อมูลแบบเงียบๆ ไม่มีจอมืด/ข้อความกระพริบอีกต่อไป ส่วนตอนผู้ใช้กดเปลี่ยน TF เองจะยังเห็น feedback ว่า "กำลังโหลด" ตามที่ควรจะเป็น (มีประโยชน์จริงตอนนั้น)

---

## ข้อ 2: ปุ่ม "เต็มจอ" กดเข้าได้แต่กดออกไม่ได้

### สาเหตุ (ยืนยันจากโค้ด)
โค้ดปุ่ม `btnFullscreen` เรียก `p.requestFullscreen()` **ทุกครั้งที่กด โดยไม่เช็คก่อนว่าตอนนี้อยู่ในโหมดเต็มจอแล้วหรือยัง** เมื่อกดซ้ำตอนอยู่ในโหมดเต็มจอ เบราว์เซอร์จะไม่ทำอะไร (เพราะขอ fullscreen ซ้ำตอนเป็น fullscreen อยู่แล้ว) ผู้ใช้เลยไม่มีทางออกจากโหมดเต็มจอผ่านปุ่มนี้เลย ต้องกด Esc เอาเองซึ่งไม่มีใครรู้

### วิธีแก้
```js
if(id==='btnFullscreen'){
  const p=document.getElementById('chartPanel');
  if(document.fullscreenElement){
    document.exitFullscreen();                 // ← เพิ่มเงื่อนไขนี้: ถ้าอยู่ในโหมดเต็มจอแล้ว ให้ออกแทน
    return;
  }
  if(p&&p.requestFullscreen){
    const wrap=document.getElementById('lwWrap'); const prev=wrap&&wrap.style.height;
    if(wrap) wrap.style.height='calc(100vh - 130px)';
    p.requestFullscreen().then(()=>{ setTimeout(v=>refreshLWResize(),80); }).catch(()=>{ if(wrap&&prev) wrap.style.height=prev; });
  }
  return;
}
```

แนะนำเพิ่ม: สลับไอคอน/label ของปุ่มตามสถานะ ให้รู้ทันทีว่ากดแล้วจะ "ขยาย" หรือ "ย่อ":
```js
document.addEventListener('fullscreenchange',()=>{
  const btn=document.getElementById('btnFullscreen');
  const icon=btn?.querySelector('i'); const lbl=btn?.querySelector('.btn-lbl');
  if(document.fullscreenElement){
    if(icon) icon.className='ti ti-minimize';
    if(lbl) lbl.textContent='ย่อจอ';
  }else{
    if(icon) icon.className='ti ti-maximize';
    if(lbl) lbl.textContent='เต็มจอ';
    const wrap=document.getElementById('lwWrap'); if(wrap) wrap.style.height='460px';
    refreshLWResize();
  }
});
```
(ลบ `document.addEventListener('fullscreenchange', ...)` เวอร์ชันเดิมที่มีอยู่แล้วออก แล้วแทนที่ด้วยอันนี้ เพราะทำหน้าที่เดิมครบ + เพิ่มสลับไอคอน)

---

## ข้อ 3 (เรื่องใหญ่ที่สุด): Indicator (RSI/ADX) ทับกับกราฟราคาแทนที่จะแยกเป็นแถบของตัวเอง

### สาเหตุ (ยืนยันจากโค้ด — เป็นความเข้าใจผิดเรื่อง API)
โค้ดปัจจุบันพยายามแยก RSI/ADX/Volume ออกจากราคาโดยใช้ `priceScaleId` คนละชื่อ (`'rsiScale'`, `'adxScale'`, `'volScale'`) ร่วมกับ `scaleMargins` เช่น:
```js
lwChart.priceScale('adxScale').applyOptions({scaleMargins:{top:0.44,bottom:0.38}});
lwChart.priceScale('rsiScale').applyOptions({scaleMargins:{top:0.66,bottom:0.18}});
```
**นี่คือความเข้าใจผิดสำคัญ**: `scaleMargins` ใน `lightweight-charts` v4 ควบคุมแค่ตำแหน่ง "แกนราคา" (Y-axis) ให้เยื้องขึ้น/ลง แต่ **เส้นกราฟของ series ทุกตัวยังคงถูกวาดบน pane เดียวกันทั้งหมด (canvas เดียวกัน ไม่มีเส้นแบ่ง ไม่มีพื้นหลังแยก)** ผลคือเส้น RSI/ADX ยังคง "ลาก" ผ่านพื้นที่แท่งเทียนอยู่ดี แค่ค่า Y ถูกบีบให้อยู่โซนล่างของพื้นที่เดียวกัน — เวลาขยายกราฟ/ซูมเข้า เส้นพวกนี้จึงดูเหมือนทับแท่งเทียนโดยตรง เพราะทางเทคนิคมันคือ pane เดียวกันจริงๆ ไม่ใช่แค่ปัญหา CSS

### วิธีแก้ — เลือกได้ 2 ทาง

**ทางเลือก A (แนะนำ ถูกต้องตรงจุดที่สุด): อัปเกรดเป็น `lightweight-charts` v5**
v5 มี native Panes API ให้แยกแถบกราฟจริงในไลบรารีเดียวกัน (แบบเดียวกับที่ TradingView เว็บจริงทำ) ไม่ต้องแฮกด้วย scaleMargins อีกต่อไป
```bash
npm install lightweight-charts@5
```
โครงสร้างคร่าวๆ (API เปลี่ยนจาก `addLineSeries()`/`addCandlestickSeries()` เป็น `addSeries(Type, options, paneIndex)`):
```js
import { createChart, CandlestickSeries, LineSeries, HistogramSeries } from 'lightweight-charts';

const chart = createChart(el, {...});
const candleSeries = chart.addSeries(CandlestickSeries, {...}, 0);        // pane 0 = ราคาหลัก
const rsiSeries    = chart.addSeries(LineSeries, {color:'#9C6FE0'}, 1);   // pane 1 = RSI (แถบใหม่แยกจากราคา)
const adxSeries    = chart.addSeries(LineSeries, {color:'#FF9800'}, 2);   // pane 2 = ADX
const volSeries    = chart.addSeries(HistogramSeries, {...}, 3);         // pane 3 = Volume

// กำหนดความสูงแต่ละแถบ
chart.panes()[0].setHeight(320);  // ราคา
chart.panes()[1].setHeight(90);   // RSI
chart.panes()[2].setHeight(90);   // ADX
chart.panes()[3].setHeight(70);   // Volume
```
แต่ละ pane มีพื้นหลัง เส้นตาราง และแกนราคาของตัวเองจริงๆ ไม่ทับกับราคาอีกต่อไป และ pan/zoom ของทุก pane sync กันอัตโนมัติในตัว (ไม่ต้องเขียน sync เอง)

**ข้อควรระวัง**: v5 เปลี่ยน API หลายจุด (`addCandlestickSeries()`→`addSeries(CandlestickSeries,...)` เป็นต้น) ต้องไล่แก้ทุกจุดที่เรียก `addXxxSeries()` ในไฟล์ ไม่ใช่แค่ตรง indicator — ควรทดสอบทุกฟีเจอร์กราฟหลังอัปเกรด (marker, price line, S/R, crosshair legend)

**ทางเลือก B (เร็วกว่า ไม่ต้องอัปเกรดเวอร์ชัน): แยกเป็นกราฟคนละ instance แล้ว sync กัน**
สร้าง `createChart()` แยก 3-4 อัน (ราคา, RSI, ADX, Volume) ใน `<div>` คนละกล่อง เรียงซ้อนกันแนวตั้ง แล้ว sync การซูม/เลื่อนด้วย `subscribeVisibleLogicalRangeChange` — ดูโค้ดตัวอย่างเต็มในไฟล์แนบ `multi-pane-chart-demo.html` (ทำ pattern นี้ไว้ให้แล้วสำหรับ Volume ตั้งแต่ demo แรกที่เคยส่งไป แค่ทำซ้ำแบบเดียวกันกับ RSI และ ADX)

ข้อดี B: ไม่กระทบโค้ดอื่นในไฟล์ที่ใช้ v4 API อยู่แล้ว เสี่ยงน้อยกว่า, ข้อเสีย: ต้องดูแล sync เอง (resize, crosshair sync ข้ามกราฟ) ซึ่งมี edge case มากกว่า native panes

**คำแนะนำ**: ถ้ามีเวลาทดสอบเต็มที่ ให้ไปทาง A (อัปเกรด v5) เพราะเป็นทางที่ "แก้หายขาด" ตรงตามที่ต้องการจริงๆ ไม่ใช่การแก้ปะ ถ้าเวลาจำกัดให้ทำ B ไปก่อนแล้วค่อยย้ายเป็น A ทีหลัง

---

## ข้อ 4: Fractal จุดสูง/จุดต่ำ สีเดียวกันแยกไม่ออก

### สาเหตุ (ยืนยันจากโค้ด)
```js
fractalMarkers=fractal(nd,7,7).map(p=>({
  time:bars[p.i].time,
  position:p.t==='H'?'aboveBar':'belowBar',
  color:'#8A94A6',        // ← สีเดียวกันทั้ง High และ Low
  shape:p.t==='H'?'arrowDown':'arrowUp',
  text:'',
}));
```
ทั้งจุดสูง (`H`) และจุดต่ำ (`L`) ใช้สีเทาเดียวกันหมด แยกได้แค่จากทิศทางลูกศรเล็กๆ ซึ่งมองยากมากในจอเล็ก

### วิธีแก้
ให้สีตามความหมาย (สูง = แนวต้าน ใช้โทนอุ่น, ต่ำ = แนวรับ ใช้โทนเย็น สอดคล้องกับสีที่ใช้อยู่แล้วในระบบ ไม่ต้องเพิ่มสีใหม่):
```js
fractalMarkers=fractal(nd,7,7).map(p=>({
  time:bars[p.i].time,
  position:p.t==='H'?'aboveBar':'belowBar',
  color:p.t==='H'?'#FF9800':'#26A69A',   // High = ส้ม(แนวต้าน) / Low = เขียว(แนวรับ) — ใช้สีที่มีอยู่แล้วในระบบ
  shape:p.t==='H'?'arrowDown':'arrowUp',
  text:'',
}));
```
และอัปเดต legend ที่อธิบาย Fractal ด้านล่างกราฟ (บรรทัดที่มี `<span><i style="background:#787B86;"></i>Fractal 15</span>`) ให้แยกเป็น 2 รายการแทน 1 รายการ:
```html
<span><i style="background:#FF9800;"></i>Fractal สูง (แนวต้าน)</span>
<span><i style="background:#26A69A;"></i>Fractal ต่ำ (แนวรับ)</span>
```

---

## หมายเหตุเชิงสถาปัตยกรรม (สำคัญ ป้องกันบั๊กแบบนี้เกิดซ้ำ)

`bindLWChart()` (ซึ่งเป็นจุดที่ผูก `subscribeClick` สำหรับฟีเจอร์ "เพิ่ม S/R") ถูกเรียกเป็นบรรทัดสุดท้ายของ `initLWChart()` **ถ้ามีจุดไหนก่อนหน้านั้นใน `initLWChart()` throw error (เช่น การตั้งค่า indicator/priceScale ที่ผิดพลาด) โค้ดจะหยุดทำงานกลางคันและไม่มีวันไปถึง `bindLWChart()` เลย** ทำให้ฟีเจอร์คลิกเพิ่ม S/R ใช้งานไม่ได้ทั้งที่ปุ่ม toggle เองดูเหมือนทำงานปกติ (เพราะปุ่ม toggle ผูกอยู่คนละฟังก์ชันคือ `bindChartToolbar()`)

แนะนำให้ทำสองอย่าง:
1. ย้าย `bindLWChart()` ให้ถูกเรียกทันทีหลังสร้าง `lwChart`/`lwCandle` เสร็จ (ก่อนตั้งค่า indicator เพิ่มเติมทั้งหมด) แทนที่จะเป็นบรรทัดสุดท้าย เพื่อให้ฟีเจอร์คลิกพื้นฐานทำงานได้แน่นอนไม่ว่า indicator ส่วนอื่นจะพังหรือไม่
2. ห่อส่วนตั้งค่า indicator (EMA/BB/RSI/ADX/Volume) แต่ละตัวด้วย `try{...}catch(e){console.error('indicator setup fail',e)}` แยกทีละตัว จะได้รู้ชัดว่าตัวไหนพังจริง แทนที่จะปล่อยให้ error หนึ่งจุดทำให้ทั้งกราฟ/ปุ่มพังยกแผง

โค้ดปรับ:
```js
function initLWChart(){
  if(!window.LightweightCharts) return null;
  const el=document.getElementById('candleChart');
  if(lwChart) return;
  lwChart=LightweightCharts.createChart(el,{...});
  lwCandle=lwChart.addCandlestickSeries({...});
  bindLWChart();          // ← ย้ายมาเรียกทันทีหลังมี lwChart/lwCandle พร้อมใช้งาน
  try{ lwEma50=lwChart.addLineSeries({...}); /* ...ema ต่างๆ... */ }catch(e){ console.error('ema setup fail',e); }
  try{ lwBbU=lwChart.addLineSeries({...}); /* ...bb... */ }catch(e){ console.error('bb setup fail',e); }
  try{
    lwRsi=lwChart.addLineSeries({...priceScaleId:'rsiScale'...});
    lwChart.priceScale('rsiScale').applyOptions({scaleMargins:{top:0.66,bottom:0.18}});
  }catch(e){ console.error('rsi setup fail',e); }
  try{
    lwAdx=lwChart.addLineSeries({...priceScaleId:'adxScale'...});
    lwChart.priceScale('adxScale').applyOptions({scaleMargins:{top:0.44,bottom:0.38}});
  }catch(e){ console.error('adx setup fail',e); }
  try{
    lwVol=lwChart.addHistogramSeries({...priceScaleId:'volScale'...});
    lwChart.priceScale('volScale').applyOptions({scaleMargins:{top:0.86,bottom:0}});
  }catch(e){ console.error('volume setup fail',e); }
  _lwOHLClegend();
}
```
(หมายเหตุ: ถ้าทำตามข้อ 3 ทางเลือก A แล้ว โค้ดส่วนนี้จะถูกเขียนใหม่เป็น multi-pane อยู่ดี แพทเทิร์น try/catch แยกทีละ indicator ยังคงควรใช้เหมือนกัน)

---

## สรุปลำดับที่ควรทำ
1. แก้ข้อ 1 (loading overlay) — เร็ว ไม่เสี่ยง ทำก่อนเลย
2. แก้ข้อ 2 (fullscreen toggle) — เร็ว ไม่เสี่ยง
3. แก้ข้อ 4 (สี fractal) — เร็ว ไม่เสี่ยง
4. ทำ defensive try/catch ใน `initLWChart()` ตามหมายเหตุสถาปัตยกรรม — ช่วยให้ debug ข้อ 3 ง่ายขึ้นและป้องกันบั๊กชนิดนี้ในอนาคต
5. แก้ข้อ 3 (multi-pane) — ใช้เวลามากสุด ให้ทำหลังสุดและทดสอบละเอียดที่สุด (ดู `multi-pane-chart-demo.html` แนบประกอบ)
