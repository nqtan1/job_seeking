import {
  GoogleAuthProvider,
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

export const signInWithGoogle = () => {
  const provider = new GoogleAuthProvider()
  // Always show Google's account chooser; otherwise a browser with one active Google session
  // signs in with it silently, and the user cannot pick another account.
  provider.setCustomParameters({ prompt: 'select_account' })
  return signInWithPopup(auth, provider)
}

export const signInWithEmail = (email: string, password: string) =>
  signInWithEmailAndPassword(auth, email, password)

export async function signUpWithEmail(email: string, password: string) {
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
