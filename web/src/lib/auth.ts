import {
  EmailAuthProvider,
  GoogleAuthProvider,
  browserLocalPersistence,
  browserSessionPersistence,
  linkWithCredential,
  linkWithPopup,
  reauthenticateWithCredential,
  reauthenticateWithPopup,
  setPersistence,
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as fbSignOut,
  type User,
} from 'firebase/auth'
import { useEffect, useState } from 'react'
import type { Key } from '@/i18n'
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

/** Always show Google's account chooser; otherwise a browser with one active Google session
 *  signs in with it silently, and the user cannot pick another account. */
const googleProvider = () => {
  const provider = new GoogleAuthProvider()
  provider.setCustomParameters({ prompt: 'select_account' })
  return provider
}

export const signInWithGoogle = async (remember = false) => {
  await applyPersistence(remember)
  return signInWithPopup(auth, googleProvider())
}

export async function signInWithEmail(email: string, password: string, remember = false) {
  await applyPersistence(remember)
  return signInWithEmailAndPassword(auth, email, password)
}

/** The account exists once this resolves; a mail that cannot be sent must not look like a failed
 *  sign-up (the user would retry and hit "already in use"). It can be resent from Settings. */
export async function signUpWithEmail(email: string, password: string, remember = false) {
  await applyPersistence(remember)
  const cred = await createUserWithEmailAndPassword(auth, email, password)
  try {
    await sendEmailVerification(cred.user)
  } catch {
    /* resendable from Settings */
  }
  return cred
}

/** Same answer whether or not the address has an account (the SDK hides it on purpose). */
export const sendPasswordReset = (email: string) => sendPasswordResetEmail(auth, email)

export const resendVerification = async () => {
  if (auth.currentUser) await sendEmailVerification(auth.currentUser)
}

/** How the signed-in user can sign in: Google, a password, or both. */
export function signInMethods() {
  const user = auth.currentUser
  const has = (id: string) => !!user?.providerData.some((p) => p.providerId === id)
  return {
    email: user?.email ?? null,
    verified: !!user?.emailVerified,
    google: has('google.com'),
    password: has('password'),
  }
}

/** Gives a Google account a password too (same account, same data). Linking is sensitive, so a
 *  stale sign-in is renewed once through Google and the link retried. */
export async function addPassword(password: string) {
  const user = auth.currentUser
  if (!user?.email) throw new Error('not signed in')
  const credential = EmailAuthProvider.credential(user.email, password)
  try {
    await linkWithCredential(user, credential)
  } catch (e) {
    if ((e as { code?: string }).code !== 'auth/requires-recent-login') throw e
    await reauthenticate()
    await linkWithCredential(user, credential)
  }
  await user.reload() // providers and the verified flag as the server now has them
}

/** Lets a password account sign in with Google as well. */
export async function connectGoogle() {
  const user = auth.currentUser
  if (!user) throw new Error('not signed in')
  await linkWithPopup(user, googleProvider())
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
  if (password !== undefined && usesPassword() && user.email) {
    await reauthenticateWithCredential(
      user,
      EmailAuthProvider.credential(user.email, password ?? ''),
    )
  } else {
    await reauthenticateWithPopup(user, googleProvider())
  }
  await user.getIdToken(true)
}

const ERRORS: Record<string, Key> = {
  'auth/invalid-credential': 'auth.err.credentials',
  'auth/user-not-found': 'auth.err.credentials',
  'auth/wrong-password': 'auth.err.credentials',
  'auth/email-already-in-use': 'auth.err.exists',
  'auth/weak-password': 'auth.err.weak',
  'auth/invalid-email': 'auth.email_invalid',
  'auth/too-many-requests': 'auth.err.too_many',
  'auth/user-disabled': 'auth.err.disabled',
  'auth/account-exists-with-different-credential': 'auth.err.other_method',
  'auth/credential-already-in-use': 'auth.err.other_account',
  'auth/provider-already-linked': 'auth.err.linked',
  'auth/popup-closed-by-user': 'auth.err.cancelled',
  'auth/cancelled-popup-request': 'auth.err.cancelled',
  'auth/popup-blocked': 'auth.err.popup',
  'auth/network-request-failed': 'auth.err.network',
  'auth/requires-recent-login': 'auth.err.reauth',
  'auth/user-token-expired': 'auth.err.reauth',
}

/** Never show raw SDK text: map the error code or fall back to a generic message. */
export const authErrorKey = (e: unknown): Key =>
  ERRORS[(e as { code?: string }).code ?? ''] ?? 'auth.err.generic'
