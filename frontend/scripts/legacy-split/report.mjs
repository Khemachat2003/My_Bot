// report.mjs — สรุปจาก analyze.mjs: ตัวแปร top-level แต่ละตัว ประกาศที่ไหน ถูกอ่าน/เขียนที่บรรทัดใด
// รัน: node scripts/legacy-split/report.mjs <ast.json> <out.txt>
import { readFileSync, writeFileSync } from 'node:fs';
const [, , astPath, outPath] = process.argv;
const a = JSON.parse(readFileSync(astPath, 'utf8'));
const out = [];
for (const [name, v] of Object.entries(a.vars).sort((x, y) => x[1].line - y[1].line)) {
  const reads = v.refs.filter((r) => !r.write).map((r) => r.line);
  const writes = v.refs.filter((r) => r.write && !r.init).map((r) => r.line);
  out.push(`${v.line}\t${v.kind}\t${name}\tR:${reads.join(',') || '-'}\tW:${writes.join(',') || '-'}`);
}
out.push('', 'STATEMENTS:');
for (const s of a.stmts) out.push(`${s.start}-${s.end}\t${s.type}`);
writeFileSync(outPath, out.join('\n'));
console.log('ok');
