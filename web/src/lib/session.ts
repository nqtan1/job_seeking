/** Client side of the session policy (ADR 0024): the idle timer and "sign out everywhere". The
 *  server enforces the absolute lifetime and step-up from the token; idle lives here. */
import { useEffect, useRef, useState } from 'react'

const ACTIVITY_KEY = 'session:last-activity'
const CHANNEL = 'session'
export const WARN_BEFORE_MS = 2 * 60_000

export type IdleState = 'active' | 'warning' | 'expired'

/** Pure so the boundaries are testable: warning in the last 2 minutes, expired at the limit. */
export function idleState(now: number, lastActivity: number, limitMs: number): IdleState {
  const idle = now - lastActivity
  if (idle >= limitMs) return 'expired'
  return idle >= limitMs - WARN_BEFORE_MS ? 'warning' : 'active'
}

const readShared = (): number => {
  try {
    return Number(localStorage.getItem(ACTIVITY_KEY)) || 0
  } catch {
    return 0
  }
}
const writeShared = (t: number) => {
  try {
    localStorage.setItem(ACTIVITY_KEY, String(t))
  } catch {
    /* this tab's own clock is used */
  }
}

export type EndReason = 'idle' | 'reauth' | 'other-tab'
let endHandler: ((reason: EndReason) => void) | undefined
/** The guard registers how to end the session (clear caches, sign out, go to /signin). */
export const registerEndSession = (fn: ((reason: EndReason) => void) | undefined) => {
  endHandler = fn
}
export const endSession = (reason: EndReason) => endHandler?.(reason)

// Signing out flips the auth state, and the route guard redirects to /signin before we can add
// a query string: the reason travels here instead, and the sign-in page picks it up once.
let pendingReason: EndReason | undefined
export const setEndReason = (r: EndReason) => {
  pendingReason = r
}
export const peekEndReason = () => pendingReason
export const clearEndReason = () => {
  pendingReason = undefined
}

// One channel per tab: a message is delivered to the other tabs, never echoed back to this one.
const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(CHANNEL)
export const broadcastSignOut = () => channel?.postMessage('signed_out')

/** Tracks activity and reports `active | warning | expired`. `touch` = "Stay signed in". */
export function useIdleSession(limitMinutes: number, enabled: boolean) {
  const limitMs = limitMinutes * 60_000
  const last = useRef(Date.now())
  const [state, setState] = useState<IdleState>('active')
  const [secondsLeft, setSecondsLeft] = useState(0)

  const touch = () => {
    last.current = Date.now()
    writeShared(last.current)
    setState('active')
  }

  useEffect(() => {
    if (!enabled) return
    touch()
    let throttled = 0
    const onActivity = () => {
      const now = Date.now()
      if (now - throttled < 5_000) return
      throttled = now
      // Once the warning is up only the dialog's button counts: moving the mouse must not hide it.
      if (idleState(now, Math.max(last.current, readShared()), limitMs) === 'active') touch()
    }
    const events = ['pointerdown', 'keydown', 'scroll', 'touchstart'] as const
    events.forEach((e) => window.addEventListener(e, onActivity, { passive: true }))
    const tick = () => {
      const lastSeen = Math.max(last.current, readShared()) // another tab may have been active
      const now = Date.now()
      const next = idleState(now, lastSeen, limitMs)
      setState(next)
      if (next !== 'active')
        setSecondsLeft(Math.max(0, Math.ceil((lastSeen + limitMs - now) / 1000)))
      if (next === 'expired') endSession('idle')
    }
    const timer = window.setInterval(tick, 1_000)
    document.addEventListener('visibilitychange', tick) // a sleeping laptop expires on wake
    return () => {
      events.forEach((e) => window.removeEventListener(e, onActivity))
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limitMs, enabled])

  return { state, secondsLeft, touch }
}

/** Another tab signed out: this one follows. */
export function useSignOutBroadcast(onSignedOut: () => void) {
  useEffect(() => {
    const listener = () => onSignedOut()
    channel?.addEventListener('message', listener)
    return () => channel?.removeEventListener('message', listener)
  }, [onSignedOut])
}
