// eslint.config.js — lint frontend (flat config)
// โค้ดใน src/features/** ย้ายมาจาก index.html เดิมแบบ move-only (Phase A) จึงลด rule
// บางตัวเป็น warn ไว้ก่อน — Phase C จะเก็บกวาดทีละไฟล์
import js from '@eslint/js';
import globals from 'globals';

export default [
  { ignores: ['dist/**', 'node_modules/**', 'vendor/**', 'demos/**', 'test-results/**', 'playwright-report/**'] },
  js.configs.recommended,
  {
    files: ['src/**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser, LightweightCharts: 'readonly' },
    },
    rules: {
      'no-unused-vars': ['warn', { args: 'none', caughtErrors: 'none' }],
      'no-empty': ['warn', { allowEmptyCatch: true }],
      // Phase A = move-only: โค้ดจาก index.html เดิม throw แบบไม่แนบ cause — เก็บไว้ก่อน (Phase C ค่อยจัด)
      'preserve-caught-error': 'off',
    },
  },
  {
    files: ['*.config.js', 'scripts/**/*.mjs', 'tests/**/*.{js,mjs}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.node, ...globals.browser },
    },
  },
];
