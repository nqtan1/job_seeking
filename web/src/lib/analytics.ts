import type { Middleware } from 'openapi-fetch'
import type { PostHog } from 'posthog-js'

/** The only events we send (ADR 0040). They carry no properties of ours: no text, no ids. */
export type Event =
  | 'signed_up'
  | 'cv_uploaded'
  | 'cv_reviewed'
  | 'job_added'
  | 'fit_checked'
  | 'letter_made'
  | 'applied'
  | 'chat_sent'
  | 'flow_run'
  | 'tool_opened'

const STORE = 'analytics-consent'
export type Consent = 'yes' | 'no'

/** Off unless the build sets `VITE_POSTHOG_KEY` (empty in dev, tests and CI). */
export const analyticsAvailable = () => Boolean(import.meta.env.VITE_POSTHOG_KEY)

export function getConsent(): Consent | null {
  try {
    const v = localStorage.getItem(STORE)
    return v === 'yes' || v === 'no' ? v : null
  } catch {
    return null
  }
}

let client: Promise<PostHog> | undefined

export function setConsent(c: Consent) {
  try {
    localStorage.setItem(STORE, c)
  } catch {
    /* not stored: asked again next visit */
  }
  // a "no" after a "yes": stop the loaded SDK and wipe its stored id (ph_* in localStorage)
  if (c === 'no')
    void client?.then((p) => {
      p.opt_out_capturing()
      p.reset()
    })
}

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi

/** PostHog adds the page URL and referrer itself: keep the route shape, drop ids and queries. */
function cleanProps(props?: Record<string, unknown>) {
  for (const [k, v] of Object.entries(props ?? {}))
    if (typeof v === 'string' && /url|pathname|referr/i.test(k))
      props![k] = v.split(/[?#]/)[0].replace(UUID, ':id')
}

/** Loads PostHog the first time an event is sent with consent; never before. */
function load() {
  if (!analyticsAvailable() || getConsent() !== 'yes') return undefined
  client ??= import('posthog-js').then(({ default: posthog }) => {
    posthog.init(import.meta.env.VITE_POSTHOG_KEY, {
      api_host: 'https://eu.i.posthog.com',
      person_profiles: 'identified_only', // and we never identify: every visitor stays anonymous
      persistence: 'localStorage',
      autocapture: false,
      capture_pageview: false,
      capture_pageleave: false,
      disable_session_recording: true,
      disable_surveys: true,
      capture_heatmaps: false,
      capture_dead_clicks: false,
      capture_exceptions: false,
      advanced_disable_flags: true,
      disable_external_dependency_loading: true,
      save_referrer: false,
      before_send: (e) => {
        cleanProps(e?.properties)
        cleanProps(e?.$set)
        cleanProps(e?.$set_once)
        return e
      },
    })
    return posthog
  })
  return client
}

/** A no-op without the key or without consent (a later "no" also stops the events). */
export const track = (event: Event) => void load()?.then((p) => p.capture(event))

/** One row per successful API call that counts as a product event (method + OpenAPI path). */
const EVENTS: Record<string, Event> = {
  'POST /api/v1/cv-reviews': 'cv_reviewed',
  'POST /api/v1/cv-reviews/recheck': 'cv_reviewed',
  'POST /api/v1/jobs': 'job_added',
  'POST /api/v1/jobs/from-file': 'job_added',
  'POST /api/v1/fit-analyses': 'fit_checked',
  'POST /api/v1/letters': 'letter_made',
  'POST /api/v1/flows/{flow_id}/runs': 'flow_run',
  'POST /api/v1/flow-runs/{run_id}/rerun': 'flow_run',
}
// Counted only when the application ends up "applied" (a planned one is not).
const APPLIED = new Set([
  'POST /api/v1/applications',
  'POST /api/v1/applications/{application_id}/status',
])

export const analyticsMiddleware: Middleware = {
  async onResponse({ request, schemaPath, response }) {
    if (!response.ok || !analyticsAvailable() || getConsent() !== 'yes') return
    const key = `${request.method} ${schemaPath}`
    if (EVENTS[key]) track(EVENTS[key])
    else if (APPLIED.has(key)) {
      const body = await response
        .clone()
        .json()
        .catch(() => null)
      if (body?.status === 'applied') track('applied')
    }
  },
}
