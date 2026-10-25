import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initAppCheck } from './lib/app-check'

initAppCheck()
// Wake a scaled-to-zero API now, in parallel with the app loading and the sign-in, instead of
// on the first authenticated request (a cold start takes ~14 s). Cheap, public, ignored on error.
fetch('/api/ping', { cache: 'no-store' }).catch(() => {})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
