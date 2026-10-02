// format ทิศทาง/margin ของสัญญาณ
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1201–1204 แบบ move-only

function dirClass(d){ return d==='CALL'?'dir-call':(d==='PUT'?'dir-put':''); }
function marginColor(m){ if(m==null||isNaN(m)) return 'muted'; if(m>1) return 'green'; if(m<-1) return 'red'; return 'yellow'; }
function fmtMargin(m){ return m==null?'–':(m>0?'+':'')+m+'pp'; }


export { dirClass, fmtMargin };
