/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import solid from 'vite-plugin-solid'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [solid(), tailwindcss()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
  server: {
    host: '127.0.0.1',
    port: 1421,
    strictPort: true,
    proxy: {
      '/api/v1': {
        target: 'http://127.0.0.1:8001',
      },
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
