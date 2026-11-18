import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vitest/config'

// `API_URL` lets an isolated end-to-end stack run beside the everyday dev servers.
const api = process.env.API_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  // `/_dev/storage` serves LocalStorage files (signed links) in dev; prod uses absolute GCS URLs.
  // React + router are ~300 KB of the entry; their own chunk keeps the entry under the budget
  // (scripts/bundle-budget.mjs) and stays cached across app deploys. Same bytes on a cold load.
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) =>
          /node_modules\/(react|react-dom|react-router|scheduler)\//.test(id) ? 'react' : undefined,
      },
    },
  },
  server: { proxy: { '/api': api, '/_dev': api } },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
  },
})
