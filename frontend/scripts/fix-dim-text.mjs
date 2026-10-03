// fix-dim-text.mjs — แทน color:var(--dim) (ใช้กับข้อความ) เป็น color:var(--muted) ตามกฎ design_system C-1
import { readFileSync, writeFileSync } from 'node:fs';
const files = [
  'src/app/layout.css', 'src/features/chart/chart-base.css', 'src/features/gauges/gauges.css',
  'src/features/ml-signals/feed.css', 'src/features/setup-signals/setup-guide.css',
  'src/features/status-bar/topbar.css', 'src/features/watchlist/watchlist.css',
  'src/shared/ui/report-layout.css', 'src/shared/ui/tables.css',
];
let total = 0;
for (const f of files) {
  const p = new URL('../' + f, import.meta.url);
  const s = readFileSync(p, 'utf8');
  const n = s.split('color:var(--dim)').length - 1;
  if (n) writeFileSync(p, s.replaceAll('color:var(--dim)', 'color:var(--muted)'));
  total += n;
  console.log(f, n);
}
console.log('total replaced:', total);