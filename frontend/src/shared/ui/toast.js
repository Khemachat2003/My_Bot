// toast มุมขวาบน (ใช้ร่วมทุก feature)
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1147–1163 แบบ move-only

function showToast(msg, type){
  let c = document.getElementById('_toast');
  if(!c){
    c = document.createElement('div');
    c.id = '_toast';
    c.style.cssText = 'position:fixed;top:16px;right:16px;z-index:9999;max-width:340px;';
    document.body.appendChild(c);
  }
  const d = document.createElement('div');
  const bg = type === 'CALL' ? '#26A69A' : type === 'PUT' ? '#EF5350' : '#2962FF';
  d.style.cssText = `background:${bg};color:#fff;padding:10px 14px;border-radius:8px;margin-bottom:8px;font-size:12px;font-family:monospace;box-shadow:0 2px 8px rgba(0,0,0,.3);opacity:0;transition:opacity .3s;`;
  d.textContent = msg;
  c.appendChild(d);
  requestAnimationFrame(()=> d.style.opacity = '1');
  setTimeout(()=> { d.style.opacity = '0'; setTimeout(()=> d.remove(), 400); }, 5000);
}


export { showToast };
