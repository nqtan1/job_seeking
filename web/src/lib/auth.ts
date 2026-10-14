import {
  EmailAuthProvider,
  GoogleAuthProvider,
  browserLocalPersistence,
  browserSessionPersistence,
  reauthenticateWithCredential,
  reauthenticateWithPopup,
  setPersistence,
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendEmailVerification,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as fbSignOut,
  type User,
} from 'firebase/auth'
import { useEffect, useState } from 'react'
import { auth } from '@/lib/firebase'

/** Where the "keep me signed in" choice is remembered, so the idle limit can follow it. A lost
 *  or unreadable value falls back to the shorter limit (fail safe). */
export const REMEMBER_KEY = 'session:remembered'
export const isRemembered = () => {
  try {
    return localStorage.getItem(REMEMBER_KEY) === '1'
  } catch {
    return false
  }
}

/** Unchecked: the session ends when the browser closes. Checked: it survives restarts. */
async function applyPersistence(remember: boolean) {
  await setPersistence(auth, remember ? browserLocalPersistence : browserSessionPersistence)
  try {
    localStorage.setItem(REMEMBER_KEY, remember ? '1' : '0')
  } catch {
    /* the shorter idle limit applies */
  }
}

export const signInWithGoogle = async (remember = false) => {
  await applyPersistence(remember)
  const provider = new GoogleAuthProvider()
  // Always show Google's account chooser; otherwise a browser with one active Google session
  // signs in with it silently, and the user cannot pick another account.
  provider.setCustomParameters({ prompt: 'select_account' })
  return signInWithPopup(auth, provider)
}

export async function signInWithEmail(email: string, password: string, remember = false) {
  await applyPersistence(remember)
  return signInWithEmailAndPassword(auth, email, password)
}

export async function signUpWithEmail(email: string, password: string, remember = false) {
  await applyPersistence(remember)
  const cred = await createUserWithEmailAndPassword(auth, email, password)
  await sendEmailVerification(cred.user)
  return cred
}

export const signOut = () => fbSignOut(auth)

/** Fresh ID token (the SDK refreshes it when expired). Never persist it ourselves. */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await auth.currentUser?.getIdToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** `undefined` = still resolving, `null` = signed out. */
export function useAuthUser(): User | null | undefined {
  const [user, setUser] = useState<User | null | undefined>(auth.currentUser ?? undefined)
  useEffect(() => onAuthStateChanged(auth, setUser), [])
  return user
}

/** Seconds since the original sign-in (the token's `auth_time`; a silent refresh keeps it). */
export async function signInAgeSeconds(): Promise<number> {
  const result = await auth.currentUser?.getIdTokenResult()
  return result ? (Date.now() - Date.parse(result.authTime)) / 1000 : Infinity
}

export const usesPassword = () =>
  !!auth.currentUser?.providerData.some((p) => p.providerId === 'password')

/** Step-up: prove it is still the account owner (Google popup, or the password), then fetch a
 *  token that carries the new `auth_time`. */
export async function reauthenticate(password?: string) {
  const user = auth.currentUser
  if (!user) throw new Error('not signed in')
  if (usesPassword() && user.email) {
    await reauthenticateWithCredential(user, EmailAuthProvider.credential(user.email, password ?? ''))
  } else {
    const provider = new GoogleAuthProvider()
    provider.setCustomParameters({ prompt: 'select_account' })
    await reauthenticateWithPopup(user, provider)
  }
  await user.getIdToken(true)
}
