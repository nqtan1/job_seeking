import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// Needs the isolated stack (backend/tests/e2e_stack.sh up). The scripted worker's "AI" is off while
// backend/.e2e-run/fail-ai exists, which this test creates and removes.
const FIXTURES = path.resolve(import.meta.dirname, '../../backend/tests/fixtures')
const AI_OFF = path.resolve(import.meta.dirname, '../../backend/.e2e-run/fail-ai')
const SHOTS = process.env.E2E_SHOTS

const menu = (page: Page, name: string | RegExp) =>
  page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name })

test.afterEach(() => fs.rmSync(AI_OFF, { force: true }))

test('radar: a run interrupted by the AI is explained, loses nothing and is retried in one click', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.goto('/')
  await page.getByRole('button', { name: 'No account? Sign up' }).click()
  await page.getByLabel('Email').fill(`retry${Date.now()}@example.com`)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign up', exact: true }).click()
  await menu(page, 'Profile').click()
  await page.getByLabel('CV file').setInputFiles(path.join(FIXTURES, 'cv_sample.pdf'))
  await page.getByRole('button', { name: 'Extract profile' }).click()
  await expect(page.getByLabel('Name', { exact: true })).not.toHaveValue('', { timeout: 120_000 })
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Profile saved.')).toBeVisible()
  await menu(page, 'Radar').click()
  await page.getByRole('button', { name: 'Start this radar' }).click()

  // The AI is down: the run finds offers but cannot score them.
  fs.mkdirSync(path.dirname(AI_OFF), { recursive: true })
  fs.writeFileSync(AI_OFF, '')
  await page.getByRole('button', { name: 'Run now' }).click()
  const alert = page.getByRole('alert').filter({ hasText: 'interrupted' })
  await expect(alert).toBeVisible({ timeout: 60_000 })
  await expect(alert).toContainText('the AI was unavailable')
  await expect(alert).toContainText('found 3 offers and scored 0. Nothing was lost')
  await expect(page.getByRole('region', { name: 'What your radar did' })).toContainText(
    'the AI was unavailable',
  )
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, '6-interrupted.png'), fullPage: true })

  // The AI is back: one click, no waiting for the cool-down, the same offers are scored.
  fs.rmSync(AI_OFF, { force: true })
  await alert.getByRole('button', { name: 'Retry now' }).click()
  await expect(page.getByRole('region', { name: 'Radar status' })).toContainText(
    /looked at 3 new offers, kept 2/,
    { timeout: 60_000 },
  )
  await expect(page.getByRole('alert').filter({ hasText: 'interrupted' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Radar status' })).toContainText('2 new matches')
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, '7-retried.png'), fullPage: true })
})
