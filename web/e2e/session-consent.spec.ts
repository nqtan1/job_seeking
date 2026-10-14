import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

// Needs the isolated stack: backend/tests/e2e_stack.sh up. Session policy (ADR 0024).
const SHOTS = process.env.E2E_SHOTS
const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true })
}

async function signUp(page: Page, remember: boolean) {
  await page.goto('/')
  await page.getByRole('button', { name: 'No account? Sign up' }).click()
  await page.getByLabel('Email').fill(`sess${Date.now()}${Math.random().toString(36).slice(2, 6)}@example.com`)
  await page.getByLabel('Password').fill('password123')
  if (remember) await page.getByLabel('Keep me signed in').check()
  await shot(page, remember ? 'login-remember' : 'login-checkbox')
  await page.getByRole('button', { name: 'Sign up', exact: true }).click()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
}

test('"keep me signed in": unchecked ends with the browser tab session, checked survives it', async ({
  browser,
}) => {
  const a = await browser.newContext()
  const pa = await a.newPage()
  await signUp(pa, false)
  const second = await a.newPage() // a new tab = a new browser session for sessionStorage
  await second.goto('/')
  await expect(second.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible()
  await a.close()

  const b = await browser.newContext()
  const pb = await b.newPage()
  await signUp(pb, true)
  const again = await b.newPage()
  await again.goto('/')
  await expect(again.getByRole('navigation', { name: 'Main' })).toBeVisible()
  await b.close()
})

test('consent, withdrawal, step-up before export, and the idle sign-out', async ({ page }) => {
  await page.clock.install()
  await page.setViewportSize({ width: 1280, height: 900 })
  await signUp(page, false)

  // Consent: unticked, disabled until ticked, then radars are on.
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Radar' }).click()
  await page.getByRole('button', { name: 'Review and enable' }).click()
  const enable = page.getByRole('button', { name: 'Enable background radars' })
  await expect(page.getByRole('checkbox', { name: /I agree/ })).not.toBeChecked()
  await expect(enable).toBeDisabled()
  await shot(page, 'consent-dialog')
  await page.getByRole('checkbox', { name: /I agree/ }).check()
  await enable.click()
  await expect(page.getByRole('button', { name: 'Review and enable' })).toBeHidden()

  // Settings: granted, then withdrawn.
  await page.goto('/settings')
  await expect(page.getByText('granted', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Withdraw consent' }).click()
  await expect(page.getByText('withdrawn', { exact: true })).toBeVisible()
  await shot(page, 'consent-settings')

  // Step-up: 6 minutes later, export asks for the password first.
  await page.clock.fastForward('06:00')
  await page.getByRole('button', { name: 'Request export' }).click()
  const dialog = page.getByRole('dialog', { name: 'Confirm it is you' })
  await expect(dialog).toBeVisible()
  await shot(page, 'step-up')
  await dialog.getByLabel('Password').fill('password123')
  await dialog.getByRole('button', { name: 'Confirm' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText(/Preparing your export|Download your export/)).toBeVisible()

  // Idle: warning two minutes before the 30-minute limit, sign-out at the limit.
  await page.clock.fastForward('28:30')
  const warning = page.getByRole('dialog', { name: 'Stay signed in?' })
  await expect(warning).toBeVisible()
  await shot(page, 'idle-warning')
  await page.clock.fastForward('02:00')
  await expect(page).toHaveURL(/\/signin$/)
  await expect(page.getByText('You were signed out because of inactivity.')).toBeVisible()
  await shot(page, 'idle-signed-out')
})
