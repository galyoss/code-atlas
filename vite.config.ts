import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// The scan API has no CORS policy, so Atlas reaches it through a same-origin proxy.
const scanApi = {
  '/api': {
    target: process.env.SCAN_API_URL || 'http://127.0.0.1:8080',
    rewrite: (path: string) => path.replace(/^\/api/, ''),
  },
};

export default defineConfig({
  plugins: [react()],
  server: { proxy: scanApi },
  preview: { proxy: scanApi },
  // Ignored local checkouts under .work carry their own test suites.
  test: { include: ['src/**/*.test.ts'] },
});
