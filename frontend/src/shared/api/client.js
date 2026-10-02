// API client กลาง — fetchJSON (timeout 15 วิ)
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1187–1200 แบบ move-only

// timeout บังคับ: ถ้า server ค้าง/ถูก reset จะ reject ใน 15 วิ แทนที่จะค้างตลอด
// (เดิมไม่มี timeout → Promise.all ค้าง → ทุกอย่างที่รออยู่หลัง await เช่น watchlist ไม่เคยทำงาน)
async function fetchJSON(url,timeoutMs=15000){
  const ac=new AbortController();
  const timer=setTimeout(()=>ac.abort(),timeoutMs);
  try{
    const res=await fetch(url,{signal:ac.signal,cache:'no-store'});
    if(!res.ok) throw new Error(url+' → '+res.status);
    return await res.json();
  }catch(e){
    if(e&&e.name==='AbortError') throw new Error(url+' → timeout '+timeoutMs+'ms');
    throw e;
  }finally{ clearTimeout(timer); }
}

export { fetchJSON };
