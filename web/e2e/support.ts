import AxeBuilder from '@axe-core/playwright'
import { expect, type Page } from '@playwright/test'
import path from 'node:path'

// Synthetic fixtures only.
export const FIXTURES = path.resolve(import.meta.dirname, '../../backend/tests/fixtures')

/** The phone layout (below Tailwind `md`): the places are a bottom tab bar, the sidebar a drawer. */
export const narrow = (page: Page) => (page.viewportSize()?.width ?? 1280) < 768

/** The place menu on screen: the sidebar ("Main") on a desktop, the bottom tabs ("Places") on a phone. */
export const places = (page: Page) => page.getByRole('navigation', { name: /^(Main|Places)$/ })

export async function signUp(page: Page, prefix: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'No account? Sign up' }).click()
  await page.getByLabel('Email').fill(`${prefix}${Date.now()}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill('password123')
  await page.getByLabel('Confirm password').fill('password123')
  await page.getByRole('button', { name: 'Sign up', exact: true }).click()
  await expect(places(page)).toBeVisible()
}

/** Tools, then a career card (its name starts the link text). */
export async function career(page: Page, card: string) {
  await places(page).getByRole('link', { name: 'Tools', exact: true }).click()
  await page
    .getByRole('region', { name: 'Career' })
    .getByRole('link', { name: new RegExp(`^${card}`) })
    .click()
}

/** The canned profile from the CV fixture, saved (the chat needs one). */
export async function saveProfileFromCv(page: Page) {
  await career(page, 'CV')
  await page.getByLabel('CV file').setInputFiles(path.join(FIXTURES, 'cv_sample.pdf'))
  await page.getByRole('button', { name: 'Extract profile' }).click()
  await expect(page.getByLabel('Name', { exact: true })).not.toHaveValue('', { timeout: 120_000 })
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Profile saved.')).toBeVisible()
}

/** WCAG 2.2 AA, serious and critical only: the end of every spec. */
export async function expectNoA11yViolations(page: Page) {
  // measure the settled page: a fade-in caught half-way reads as low contrast
  await page.emulateMedia({ reducedMotion: 'reduce' })
  // runs in the browser (a string: this tsconfig has no DOM types); an endless animation must not hang
  await page.evaluate(`Promise.race([
    Promise.all(document.getAnimations().map((a) => a.finished)),
    new Promise((done) => setTimeout(done, 2000)),
  ])`)
  const { violations } = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  const bad = violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)
  expect(bad).toEqual([])
}
