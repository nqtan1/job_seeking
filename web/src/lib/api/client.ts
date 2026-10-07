import createClient from 'openapi-fetch'
import { getAppCheckHeaders } from '@/lib/app-check'
import { getAuthHeaders } from '@/lib/auth'
import type { paths } from './schema'

export const api = createClient<paths>({ baseUrl: window.location.origin })

// ID token + App Check token on every call. `X-Org-Id` is omitted: the backend defaults to the
// user's only org; add it here when an org switcher exists.
api.use({
  async onRequest({ request }) {
    const headers = { ...(await getAuthHeaders()), ...(await getAppCheckHeaders()) }
    for (const [k, v] of Object.entries(headers)) request.headers.set(k, v)
    return request
  },
})
