// split-js.mjs — แยก <script> เดิมเป็น ES modules + สร้าง import/export อัตโนมัติ
// ตรวจ: ครอบทุกบรรทัด/ไม่ซ้ำ, ไม่มีการเขียนตัวแปรข้าม module, live ไม่พึ่งโค้ด archive,
//       shared ห้าม import feature, ข้าม feature ต้องผ่าน features/<x>/index.js
import { writeFileSync } from 'node:fs';
import { resolve, posix } from 'node:path';
import * as espree from 'espree';
import * as eslintScope from 'eslint-scope';
import { JS_MODULES, ARCHIVE, ARCHIVE_JS, SCRIPT_BLOCK } from './split.js-map.mjs';
import { JS_APPEND, TODO_NOTES } from './split.edits.mjs';
import { FRONT, span, fmtRanges, fail, writeSrc, relImport, featureOf } from './split-lib.mjs';

export function splitJs(lines) {
  const L = (n) => lines[n - 1];
  const [S0, S1] = [SCRIPT_BLOCK[0] + 1, SCRIPT_BLOCK[1] - 1];
  const owner = new Map();
  for (const mod of JS_MODULES)
    for (const r of mod.ranges)
      for (const n of span(r)) {
        if (n < S0 || n > S1) fail(`${mod.file}: บรรทัด ${n} อยู่นอก <script>`);
        if (owner.has(n)) fail(`บรรทัด ${n} ซ้ำ: ${owner.get(n).file} / ${mod.file}`);
        owner.set(n, mod);
      }
  for (const n of span([S0, S1])) if (!owner.has(n)) fail(`บรรทัด ${n} ไม่มีเจ้าของ: ${L(n)}`);

  // scope analysis — แทนบรรทัดนอกสคริปต์ด้วยบรรทัดว่าง → เลขบรรทัด AST = เลขบรรทัดไฟล์เดิม
  const src = lines.map((l, i) => (i + 1 >= S0 && i + 1 <= S1 ? l : '')).join('\n');
  const ast = espree.parse(src, { ecmaVersion: 'latest', sourceType: 'module', loc: true, range: true });
  const g = eslintScope.analyze(ast, { ecmaVersion: 2022, sourceType: 'module' }).globalScope.childScopes[0];
  const imports = new Map(JS_MODULES.map((m) => [m, new Map()]));
  const exported = new Map(JS_MODULES.map((m) => [m, new Set()]));
  for (const v of g.variables) {
    if (!v.defs.length) continue;
    const home = owner.get(v.defs[0].name.loc.start.line);
    for (const r of v.references) {
      const user = owner.get(r.identifier.loc.start.line);
      if (user === home || user.file === ARCHIVE) continue;
      if (home.file === ARCHIVE) fail(`โค้ด live (${user.file}) ใช้ "${v.name}" ที่อยู่ใน archive`);
      if (r.isWrite()) fail(`${user.file} เขียนตัวแปร "${v.name}" ของ ${home.file} (ES module ทำไม่ได้)`);
      if (!imports.get(user).has(home)) imports.get(user).set(home, new Set());
      imports.get(user).get(home).add(v.name);
      exported.get(home).add(v.name);
    }
  }

  const live = JS_MODULES.filter((m) => m.file !== ARCHIVE);
  const featureIndex = new Map(); // feature → Map(file → Set(names))
  for (const mod of live) {
    const fromF = featureOf(mod.file);
    const groups = new Map();
    for (const [home, names] of imports.get(mod)) {
      const toF = featureOf(home.file);
      if (mod.file.startsWith('shared/') && toF) fail(`shared (${mod.file}) ห้าม import feature (${home.file})`);
      let target = home.file;
      if (toF && toF !== fromF) {
        target = `features/${toF}/index.js`;
        if (!featureIndex.has(toF)) featureIndex.set(toF, new Map());
        const fm = featureIndex.get(toF);
        if (!fm.has(home.file)) fm.set(home.file, new Set());
        names.forEach((n) => fm.get(home.file).add(n));
      }
      const key = relImport(mod.file, target);
      if (!groups.has(key)) groups.set(key, new Set());
      names.forEach((n) => groups.get(key).add(n));
    }
    mod.importLines = [...groups]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([p, ns]) => `import { ${[...ns].sort().join(', ')} } from '${p}';`);
  }

  const body = (ranges) => ranges.map((r) => span(r).map(L).join('\n')).join('\n');
  for (const mod of live) {
    const head = [`// ${mod.desc}`, `// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด ${fmtRanges(mod.ranges)} แบบ move-only`];
    if (TODO_NOTES[mod.file]) head.push(`// TODO: ย้ายไป backend — ${TODO_NOTES[mod.file]}`);
    const parts = [head.join('\n')];
    if (mod.importLines.length) parts.push(mod.importLines.join('\n'));
    parts.push(body(mod.ranges));
    if (JS_APPEND[mod.file]) parts.push(JS_APPEND[mod.file]);
    const ex = [...exported.get(mod)].sort();
    if (ex.length) parts.push(`export { ${ex.join(', ')} };`);
    writeSrc(mod.file, parts.join('\n\n'));
  }
  for (const [f, files] of featureIndex) {
    const own = live.filter((m) => featureOf(m.file) === f).map((m) => posix.basename(m.file));
    const out = [`// features/${f} — ทางเข้าเดียว (public API) ของ feature นี้: feature อื่น/app import ผ่านไฟล์นี้เท่านั้น`,
      `// ไฟล์ใน feature: ${own.join(', ')}`];
    for (const [file, ns] of [...files].sort()) out.push(`export { ${[...ns].sort().join(', ')} } from './${posix.basename(file)}';`);
    writeSrc(`features/${f}/index.js`, out.join('\n'));
  }
  const arch = JS_MODULES.find((m) => m.file === ARCHIVE);
  writeFileSync(resolve(FRONT, ARCHIVE_JS), [`// ARCHIVE — ${arch.desc}`,
    `// ย้ายจาก index.html เดิม บรรทัด ${fmtRanges(arch.ranges)} — ไม่ถูก import ที่ไหน เก็บไว้รอผู้ใช้อนุญาตให้ลบ`,
    '', body(arch.ranges), ''].join('\n'));

  // main.js — import ตามลำดับบรรทัดแรกของ module ในสคริปต์เดิม → side-effect ลำดับเดิม
  const order = [...live].sort((a, b) => a.ranges[0][0] - b.ranges[0][0]).map((m) => m.file);
  order.splice(order.indexOf('app/boot.js'), 0, 'shared/ui/collapsibles.js'); // แทน inline onclick
  writeSrc('main.js', ['// main.js — จุดเริ่มของ dashboard: โหลด CSS (ลำดับเดียวกับ <style> เดิม) แล้วโหลดทุก module',
    '// ลำดับ import = ลำดับโค้ดใน <script> เดิม → การผูก event / boot เกิดลำดับเดิม',
    "import './styles/index.css';", ...order.map((f) => `import './${f}';`)].join('\n'));
  return { live: live.length, features: [...featureIndex.keys()] };
}
