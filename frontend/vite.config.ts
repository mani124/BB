/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: process.env.VITE_HOST || '127.0.0.1',
    port: 5174,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
  },
});
