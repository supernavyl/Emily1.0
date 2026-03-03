/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
  server: {
    host: '127.0.0.1',
    port: 1420,
    strictPort: true,
    proxy: {
      // Routes that already have /api/v1 baked into the backend path — pass through as-is
      '/api/v1': {
        target: 'http://127.0.0.1:8001',
      },
      // Routes mounted without /api prefix (audio, memory, status, etc.) — strip /api
      '/api': {
        target: 'http://127.0.0.1:8001',
        rewrite: (path: string) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: 'ws://127.0.0.1:8001',
        ws: true,
      },
    },
  },
})
