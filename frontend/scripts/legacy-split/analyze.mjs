// analyze.mjs — วิเคราะห์ <script> ของ index.html เดิม (ใช้ตอนแยก Phase A เท่านั้น)
// ใช้ espree + eslint-scope (มากับ eslint แล้ว ไม่ต้องติดตั้งเพิ่ม)
// รัน: node scripts/legacy-split/analyze.mjs <legacy.html> <out.json>
import { readFileSync, writeFileSync } from 'node:fs';
import * as espree from 'espree';
import * as eslintScope from 'eslint-scope';

const [, , legacyPath, outPath] = process.argv;
const lines = readFileSync(legacyPath, 'utf8').split(/\r?\n/);
const SCRIPT_START = lines.findIndex((l) => l.trim() === '<script>') + 1; // 0-based index ของบรรทัดแรกในสคริปต์
const SCRIPT_END = lines.findIndex((l, i) => i > SCRIPT_START && l.trim() === '</script>');
// แทนบรรทัดก่อนหน้าสคริปต์ด้วยบรรทัดว่าง → line number ใน AST = line number ในไฟล์ html
const src = lines.map((l, i) => (i >= SCRIPT_START && i < SCRIPT_END ? l : '')).join('\n');

const ast = espree.parse(src, { ecmaVersion: 'latest', sourceType: 'script', loc: true, range: true });
const sm = eslintScope.analyze(ast, { ecmaVersion: 2022, sourceType: 'script' });
const g = sm.globalScope;

const vars = {};
for (const v of g.variables) {
  if (!v.defs.length) continue;
  const def = v.defs[0];
  vars[v.name] = {
    kind: def.type === 'FunctionName' ? 'function' : def.parent?.kind || def.type,
    line: def.name.loc.start.line,
    refs: v.references
      .filter((r) => r.identifier !== def.name)
      .map((r) => ({ line: r.identifier.loc.start.line, write: r.isWrite(), init: !!r.init, top: r.from.variableScope === g })),
  };
}
const through = g.through
  .filter((r) => !vars[r.identifier.name])
  .map((r) => ({ name: r.identifier.name, line: r.identifier.loc.start.line, write: r.isWrite() }));
const throughWrites = through.filter((r) => r.write);
const throughNames = [...new Set(through.map((r) => r.name))].sort();

// statement ระดับบนสุด
const stmts = ast.body.map((s) => ({ type: s.type, start: s.loc.start.line, end: s.loc.end.line }));

// ตรวจว่า parse เป็น module (strict) ได้ไหม
let moduleOk = true, moduleErr = '';
try { espree.parse(src, { ecmaVersion: 'latest', sourceType: 'module' }); } catch (e) { moduleOk = false; moduleErr = String(e); }

writeFileSync(outPath, JSON.stringify({ SCRIPT_START: SCRIPT_START + 1, SCRIPT_END: SCRIPT_END + 1, moduleOk, moduleErr, throughNames, throughWrites, stmts, vars }, null, 1));
console.log('ok');
