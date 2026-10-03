// fetch-fonts.mjs — ดาวน์โหลด woff2 จาก Google Fonts มา self-host ที่ src/vendor/fonts/
// ใช้ครั้งเดียวตอน C-1 (ไม่อยู่ใน build pipeline) — เก็บไว้ regenerate ได้
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url)); // frontend/scripts
const OUT = join(ROOT, '..', 'src', 'vendor', 'fonts');
mkdirSync(OUT, { recursive: true });

const CSS_URL = 'https://fonts.googleapis.com/css2'
  + '?family=IBM+Plex+Sans+Thai:wght@400;500;600'
  + '&family=IBM+Plex+Mono:wght@400;500;600'
  + '&family=Archivo:wght@600;700&display=swap';
// UA แบบ Chrome ทันสมัย → Google ตอบด้วย woff2 + unicode-range
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';

const css = await (await fetch(CSS_URL, { headers: { 'User-Agent': UA } })).text();

// parse: /* subset */ @font-face { font-family:'X'; font-style:normal; font-weight:400; src:url(...woff2) ...; unicode-range:...; }
const blocks = [...css.matchAll(/\/\* ([a-z0-9-]+) \*\/\s*@font-face\s*\{([^}]+)\}/g)];
const faces = blocks.map(([, subset, body]) => {
  const family = /font-family:\s*'([^']+)'/.exec(body)[1];
  const weight = /font-weight:\s*(\d+)/.exec(body)[1];
  const url = /src:\s*url\((\S+?\.woff2)\)/.exec(body)[1];
  const range = /unicode-range:\s*([^;]+);/.exec(body)[1];
  return { family, weight, subset, url, range };
});

// รับเฉพาะ subset ที่หน้าใช้จริง: latin + thai (ตัด latin-ext/cyrillic ฯลฯ ลดขนาด)
const WANTED = new Set(['latin', 'thai']);
const lines = [];
let total = 0;
for (const f of faces) {
  if (!WANTED.has(f.subset)) continue;
  const slug = f.family.toLowerCase().replace(/ /g, '-') + '-' + f.weight + '-' + f.subset + '.woff2';
  const dest = join(OUT, slug);
  const buf = Buffer.from(await (await fetch(f.url, { headers: { 'User-Agent': UA } })).arrayBuffer());
  writeFileSync(dest, buf);
  total += buf.length;
  lines.push(`/* ${f.family} ${f.weight} — subset: ${f.subset} */\n` +
    `@font-face{font-family:'${f.family}';font-style:normal;font-weight:${f.weight};font-display:swap;` +
    `src:url('${slug}') format('woff2');unicode-range:${f.range};}`);
  console.log('OK', slug, (buf.length / 1024).toFixed(1) + 'KB');
}
writeFileSync(join(OUT, 'fonts.css.generated'), lines.join('\n') + '\n');
console.log('TOTAL', (total / 1024).toFixed(1) + 'KB', faces.length, 'faces scanned,', lines.length / 2, 'files');