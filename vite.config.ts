import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// The scan API has no CORS policy, so Atlas reaches it through a same-origin proxy.
const scanApi = {
  '^/api/(?:health|session|auth|projects)(?:[/?]|$)': {
    target: process.env.SCAN_API_URL || 'http://127.0.0.1:8080',
    rewrite: (path: string) => path.replace(/^\/api/, ''),
  },
};

export default defineConfig({
  plugins: [react()],
  publicDir: false,
  server: {
    proxy: scanApi,
    fs: {
      deny: [
        '.env',
        '.env.*',
        '*.{crt,pem}',
        '**/.git/**',
        '**/.work/**',
        '**/data/**',
        '**/jobs/job-*/**',
        '**/.venv/**',
        '**/*.sqlite*',
        '**/*.db*',
      ],
    },
  },
  preview: { proxy: scanApi },
  // Ignored local checkouts under .work carry their own test suites.
  test: { include: ['src/**/*.test.ts'] },
});
