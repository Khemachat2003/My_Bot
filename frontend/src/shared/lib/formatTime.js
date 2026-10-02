// format เวลาแบบไทย (fmtTime / fmtHM)
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1184–1186 แบบ move-only

/* ═══════ HELPERS ═══════ */
function fmtTime(iso){ if(!iso) return '–'; return new Date(iso).toLocaleString('th-TH',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
function fmtHM(iso){ if(!iso) return '–'; return new Date(iso).toLocaleTimeString('th-TH',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }

export { fmtHM, fmtTime };
