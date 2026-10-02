// vite.config.js — build dashboard → frontend/dist (เสิร์ฟโดย backend/api.py ที่ /static/dist/)
// - base '/static/dist/' เพราะ FastAPI mount โฟลเดอร์ frontend/ ไว้ที่ /static
// - htmlInclude: ประกอบ partial HTML (<!-- @include path -->) ตอน build → DOM เหมือนไฟล์เดียวเดิม
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const ROOT = dirname(fileURLToPath(import.meta.url));
const INCLUDE_RE = /^[ \t]*<!-- @include (\S+) -->[ \t]*\r?$/gm;
const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

/** แทนบรรทัด <!-- @include src/... --> ด้วยเนื้อหาไฟล์ (ซ้อนกันได้) */
export function expandIncludes(html, depth = 0) {
  if (depth > 5) throw new Error('htmlInclude: ซ้อนลึกเกิน 5 ชั้น (วนลูป?)');
  return html.replace(INCLUDE_RE, (_m, rel) => {
    const content = readFileSync(resolve(ROOT, rel), 'utf8').replace(/\r?\n$/, '');
    return expandIncludes(content, depth + 1);
  });
}

function htmlInclude() {
  return {
    name: 'html-include',
    transformIndexHtml: { order: 'pre', handler: (html) => expandIncludes(html) },
    handleHotUpdate({ file, server }) {
      if (file.endsWith('.html')) server.ws.send({ type: 'full-reload' });
    },
  };
}

export default defineConfig({
  root: ROOT,
  base: '/static/dist/',
  plugins: [htmlInclude()],
  build: { outDir: 'dist', emptyOutDir: true, sourcemap: false },
  server: {
    // dev: หน้าเว็บจาก Vite, API/login/vendor จาก backend ตัวจริง (uvicorn :8000)
    proxy: {
      '/api': BACKEND,
      '/login': BACKEND,
      '/logout': BACKEND,
      '/static/vendor': BACKEND,
    },
  },
});
