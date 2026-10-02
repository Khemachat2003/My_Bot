// split.mjs — Phase A: แยก _archive/index.legacy.html → frontend/index.html (shell) + frontend/src/**
// move-only: ตัดตามช่วงบรรทัด (split.*-map.mjs) ไม่แก้โค้ดในบรรทัด ยกเว้น inline onclick (split.edits.mjs)
// รัน (จาก frontend/): node scripts/legacy-split/split.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { CSS_FILES, HTML_PARTIALS, STYLE_BLOCK } from './split.layout-map.mjs';
import { SCRIPT_BLOCK } from './split.js-map.mjs';
import { HTML_EDITS, JS_EDITS } from './split.edits.mjs';
import { FRONT, loadLegacy, span, fmtRanges, fail, writeSrc, relImport } from './split-lib.mjs';
import { splitJs } from './split-js.mjs';

const lines = loadLegacy();
const L = (n) => lines[n - 1];

// 1) แก้ inline onclick (จุดเดียวที่แก้ข้อความ) — log ทุกจุด
const editLog = [];
for (const [no, from, to] of [...HTML_EDITS, ...JS_EDITS]) {
  if (!L(no).includes(from)) fail(`edit บรรทัด ${no}: ไม่พบ "${from}"`);
  lines[no - 1] = L(no).replace(from, to);
  editLog.push(`  L${no}: ${from}  →  ${to}`);
}

// 2) JS
const js = splitJs(lines);

// 3) CSS — ช่วงต้องต่อเนื่องครบทั้ง <style>
let expect = STYLE_BLOCK[0] + 1;
for (const c of CSS_FILES) {
  if (c.range[0] !== expect) fail(`CSS ไม่ต่อเนื่องที่บรรทัด ${expect} (${c.file})`);
  expect = c.range[1] + 1;
  writeSrc(c.file, `/* ${c.desc} — ย้ายจาก index.html เดิม บรรทัด ${fmtRanges([c.range])} */\n` + span(c.range).map(L).join('\n'));
}
if (expect !== STYLE_BLOCK[1]) fail(`CSS ไม่ครอบถึงบรรทัด ${STYLE_BLOCK[1] - 1}`);
writeSrc('styles/index.css', [
  '/* styles/index.css — รวม CSS ทุกไฟล์ "ตามลำดับเดิม" (cascade เหมือน <style> ก้อนเดิมทุกกฎ) */',
  '/* เพิ่มไฟล์ใหม่ = แทรกตามลำดับที่ต้องการ override — ห้ามสลับลำดับเดิมโดยไม่ตรวจ screenshot */',
  ...CSS_FILES.map((c) => `@import '${relImport('styles/index.css', c.file)}';`),
].join('\n'));

// 4) HTML partials (ซ้อนกันได้) + shell
const size = (p) => p.range[1] - p.range[0];
const containing = (n) => HTML_PARTIALS.filter((p) => n >= p.range[0] && n <= p.range[1]).sort((a, b) => size(a) - size(b));
const render = (from, to, self) => {
  const out = [];
  for (let n = from; n <= to; n++) {
    const chain = containing(n); // เล็ก → ใหญ่
    const idx = self ? chain.indexOf(self) : chain.length;
    const child = idx > 0 ? chain[idx - 1] : null; // partial ลูกตรงของ self
    if (!child) { out.push(L(n)); continue; }
    if (n !== child.range[0]) fail(`partial ${child.file} ซ้อนไม่ถูกต้อง`);
    out.push(`${L(n).match(/^\s*/)[0]}<!-- @include src/${child.file} -->`);
    n = child.range[1];
  }
  return out.join('\n');
};
for (const p of HTML_PARTIALS) writeSrc(p.file, render(p.range[0], p.range[1], p));
const shellBody = render(STYLE_BLOCK[1] + 1, SCRIPT_BLOCK[0] - 1, null);
writeFileSync(resolve(FRONT, 'index.html'), [
  ...span([1, STYLE_BLOCK[0] - 1]).map(L),
  '<!-- CSS + JS ทั้งหมดอยู่ใน src/ (แยกตาม feature) — แผนที่ไฟล์: frontend/AGENTS.md / docs/code_map.md -->',
  '<script type="module" src="/src/main.js"></script>',
  shellBody,
  ...span([SCRIPT_BLOCK[1] + 1, lines.length]).map(L),
].join('\n') + '\n');

// 5) ตรวจย้อนกลับ: ประกอบ partial กลับ ต้องได้ <body> เดิม (หลังแก้ onclick) ทุกบรรทัด
const { expandIncludes } = await import('../../vite.config.js');
const rebuilt = expandIncludes(readFileSync(resolve(FRONT, 'index.html'), 'utf8')).split('\n');
const want = span([STYLE_BLOCK[1] + 1, SCRIPT_BLOCK[0] - 1]).map(L);
const at = rebuilt.indexOf(want[0]);
if (at < 0 || rebuilt.slice(at, at + want.length).join('\n') !== want.join('\n')) fail('HTML ประกอบกลับแล้วไม่ตรงของเดิม');

console.log(`✅ JS ${js.live} modules (+archive), CSS ${CSS_FILES.length} ไฟล์, HTML ${HTML_PARTIALS.length} partials — ประกอบกลับตรงเดิม`);
console.log('feature ที่มี index.js:', js.features.join(', '));
console.log('แก้ inline onclick:\n' + editLog.join('\n'));
