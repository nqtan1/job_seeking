import {
  ReCaptchaEnterpriseProvider,
  getToken,
  initializeAppCheck,
  type AppCheck,
} from 'firebase/app-check'
import { app } from '@/lib/firebase'

let appCheck: AppCheck | undefined

/** No-op without a site key (local dev: backend runs with APP_CHECK_ENFORCED=false). */
export function initAppCheck() {
  const siteKey = import.meta.env.VITE_APPCHECK_SITE_KEY
  if (!siteKey || appCheck) return
  if (import.meta.env.VITE_APPCHECK_DEBUG) {
    // Debug token is printed in the console and registered by hand in the Firebase console.
    ;(self as unknown as { FIREBASE_APPCHECK_DEBUG_TOKEN: boolean }).FIREBASE_APPCHECK_DEBUG_TOKEN =
      true
  }
  appCheck = initializeAppCheck(app, {
    provider: new ReCaptchaEnterpriseProvider(siteKey),
    isTokenAutoRefreshEnabled: true,
  })
}

export async function getAppCheckHeaders(): Promise<Record<string, string>> {
  if (!appCheck) return {}
  const { token } = await getToken(appCheck)
  return { 'X-Firebase-AppCheck': token }
}
