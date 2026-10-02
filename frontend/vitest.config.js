// vitest.config.js — unit test ของ shared/lib, shared/api (ไม่มี DOM)
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: { include: ['tests/unit/**/*.test.js'], environment: 'node' },
});
