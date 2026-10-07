import { defineConfig } from '@playwright/test'

// Needs the API (backend/tests/e2e_server.py), the Procrastinate worker, Postgres and the Firebase
// emulator already running; only the web dev server is started here.
//
// An isolated stack (other ports and database, the emulator's Firebase config, whatever is in
// `.env.local` ignored) is selected with E2E_WEB_PORT and E2E_API_URL; see backend/tests/e2e_stack.sh.
const port = Number(process.env.E2E_WEB_PORT ?? 5173)
const isolated = !!process.env.E2E_API_URL

export default defineConfig({
  testDir: 'e2e',
  // One at a time: the tests share one API, one worker queue and (the retry test) an "AI off" switch.
  workers: 1,
  timeout: 180_000,
  use: { baseURL: `http://localhost:${port}`, trace: 'retain-on-failure' },
  webServer: {
    command: `pnpm dev --port ${port}`,
    url: `http://localhost:${port}`,
    reuseExistingServer: !isolated,
    env: isolated
      ? {
          API_URL: process.env.E2E_API_URL!,
          VITE_FIREBASE_PROJECT_ID: 'demo-recruitai',
          VITE_FIREBASE_AUTH_EMULATOR_HOST: 'localhost:9099',
          VITE_FIREBASE_API_KEY: 'demo-key',
          VITE_FIREBASE_AUTH_DOMAIN: 'localhost',
          VITE_FIREBASE_APP_ID: 'demo-app',
        }
      : {},
  },
})
