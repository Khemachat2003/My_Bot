// split-lib.mjs — helper ร่วมของสคริปต์แยกไฟล์ (Phase A)
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve, posix } from 'node:path';
import { fileURLToPath } from 'node:url';

export const FRONT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const SRC = resolve(FRONT, 'src');
export const LEGACY = resolve(FRONT, '../_archive/index.legacy.html');

export function loadLegacy() {
  const lines = readFileSync(LEGACY, 'utf8').split(/\r?\n/);
  if (lines[lines.length - 1] === '') lines.pop();
  return lines;
}
export const span = ([a, b]) => Array.from({ length: b - a + 1 }, (_, i) => a + i);
export const fmtRanges = (rs) => rs.map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`)).join(', ');
export const fail = (msg) => {
  console.error('❌ ' + msg);
  process.exit(1);
};
export function writeSrc(rel, text) {
  const p = resolve(SRC, rel);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, text.replace(/\r\n/g, '\n').replace(/\n*$/, '\n'));
}
export function writeFront(rel, text) {
  const p = resolve(FRONT, rel);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, text.replace(/\r\n/g, '\n').replace(/\n*$/, '\n'));
}
export function relImport(fromFile, toFile) {
  const p = posix.relative(posix.dirname(fromFile), toFile);
  return p.startsWith('.') ? p : './' + p;
}
export const featureOf = (f) => (f.startsWith('features/') ? f.split('/')[1] : null);
