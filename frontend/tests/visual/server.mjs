// server.mjs — เซิร์ฟเวอร์จำลองสำหรับ visual test (ไม่มี backend จริง)
//   /                → UI_TARGET=legacy: _archive/index.legacy.html | อื่นๆ: frontend/dist/index.html
//   /static/vendor/* → frontend/vendor   /static/dist/* → frontend/dist
//   /api/*           → fixtures/api.json (คีย์ = path + query เรียงชื่อ — ตรงกับ capture_fixtures.py)
//   /__requests      → รายการ request /api/* ที่หน้าเว็บยิง (ไว้เทียบ network ก่อน-หลัง) แล้วล้าง
import { createServer } from 'node:http';
import { readFileSync, existsSync, statSync } from 'node:fs';
import { resolve, extname, dirname, normalize, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONT = resolve(HERE, '../..');
const PORT = Number(process.argv[2] || 4321);
const TARGET = process.env.UI_TARGET || 'dist';
const FIXTURES = JSON.parse(readFileSync(resolve(HERE, 'fixtures/api.json'), 'utf8'));
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.svg': 'image/svg+xml' };
let log = [];

const keyOf = (u) => {
  const q = [...u.searchParams].sort(([a, x], [b, y]) => (a === b ? x.localeCompare(y) : a.localeCompare(b)));
  return u.pathname + (q.length ? '?' + q.map(([k, v]) => `${k}=${v}`).join('&') : '');
};
const sendFile = (res, base, rel) => {
  const p = normalize(resolve(base, rel));
  if (!p.startsWith(base + sep) || !existsSync(p) || !statSync(p).isFile()) return res.writeHead(404).end('not found');
  res.writeHead(200, { 'Content-Type': MIME[extname(p)] || 'application/octet-stream' }).end(readFileSync(p));
};

createServer((req, res) => {
  const u = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (u.pathname === '/__health') return res.end('ok');
  if (u.pathname === '/__requests') { const out = log; log = []; return res.end(JSON.stringify(out)); }
  if (u.pathname === '/') {
    const html = TARGET === 'legacy' ? resolve(FRONT, '../_archive/index.legacy.html') : resolve(FRONT, 'dist/index.html');
    return res.writeHead(200, { 'Content-Type': MIME['.html'] }).end(readFileSync(html));
  }
  if (u.pathname.startsWith('/static/vendor/')) return sendFile(res, resolve(FRONT, 'vendor'), u.pathname.slice(15));
  if (u.pathname.startsWith('/static/dist/')) return sendFile(res, resolve(FRONT, 'dist'), u.pathname.slice(13));
  if (u.pathname.startsWith('/api/')) {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      const key = keyOf(u);
      log.push({ method: req.method, key, body: body || null });
      const fx = FIXTURES[key];
      if (!fx) return res.writeHead(404, { 'Content-Type': 'application/json' }).end('{"detail":"no fixture"}');
      res.writeHead(fx.status, { 'Content-Type': 'application/json' }).end(JSON.stringify(fx.body));
    });
    return;
  }
  res.writeHead(404).end('not found');
}).listen(PORT, '127.0.0.1', () => console.log(`visual server :${PORT} target=${TARGET}`));
