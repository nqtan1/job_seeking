import { initializeApp } from 'firebase/app'
import { connectAuthEmulator, getAuth } from 'firebase/auth'

const env = import.meta.env

export const app = initializeApp({
  apiKey: env.VITE_FIREBASE_API_KEY ?? 'demo-key',
  // The popup flow (Google) refuses to start without an authDomain, even against the emulator.
  authDomain:
    env.VITE_FIREBASE_AUTH_DOMAIN ??
    (env.VITE_FIREBASE_AUTH_EMULATOR_HOST ? 'localhost' : undefined),
  projectId: env.VITE_FIREBASE_PROJECT_ID ?? 'demo-recruitai',
  appId: env.VITE_FIREBASE_APP_ID,
})

export const auth = getAuth(app)

if (env.VITE_FIREBASE_AUTH_EMULATOR_HOST) {
  connectAuthEmulator(auth, `http://${env.VITE_FIREBASE_AUTH_EMULATOR_HOST}`, {
    disableWarnings: true,
  })
}
