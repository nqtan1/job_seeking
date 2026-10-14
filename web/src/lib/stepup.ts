/** Step-up re-authentication before a sensitive action (export, delete, radar consent, sign out
 *  everywhere). Asks only when the sign-in is older than the server's limit, so the server's
 *  `reauth_required` is the backstop and not the normal path. */
import { signInAgeSeconds } from '@/lib/auth'

type Opener = (done: (ok: boolean) => void) => void
let opener: Opener | undefined
export const registerReauthDialog = (fn: Opener | undefined) => {
  opener = fn
}

const SAFETY_S = 30 // a request must not cross the limit on its way to the server

export async function ensureRecentAuth(maxAgeSeconds: number): Promise<boolean> {
  if ((await signInAgeSeconds()) <= maxAgeSeconds - SAFETY_S) return true
  return new Promise((resolve) => (opener ? opener(resolve) : resolve(false)))
}
