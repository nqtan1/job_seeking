import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { expectNoA11yViolations, narrow, places } from './support.ts'

// Synthetic fixtures only.
const FIXTURES = path.resolve(import.meta.dirname, '../../backend/tests/fixtures')
const JD = fs.readFileSync(path.join(FIXTURES, 'live/jd_python_paris.txt'), 'utf8')

const nav = (page: Page, name: string) => places(page).getByRole('link', { name, exact: true })
/** A career page: Tools in the menu, then its card. */
const tool = async (page: Page, name: string) => {
  await nav(page, 'Tools').click()
  await page
    .getByRole('region', { name: 'Career' })
    .getByRole('link', { name: new RegExp(`^${name}`) })
    .click()
}

test('v1 journey: sign up → profile → job → fit → letter → tracker → export → delete account', async ({
  page,
}) => {
  const email = `e2e${Date.now()}@example.com`
  const problems: string[] = []
  page.on('pageerror', (e) => problems.push(e.message))

  // Sign up (Firebase emulator) lands on the profile onboarding.
  await page.goto('/jobs')
  await expect(page).toHaveURL(/\/signin/) // route guard
  await page.getByRole('button', { name: 'No account? Sign up' }).click()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill('password123')
  await page.getByLabel('Confirm password').fill('password124')
  await page.getByRole('button', { name: 'Sign up', exact: true }).click()
  await expect(page.getByText('The two passwords are not the same.')).toBeVisible() // nothing created
  await page.getByLabel('Confirm password').fill('password123')
  await page.getByRole('button', { name: 'Sign up', exact: true }).click()
  await expect(places(page)).toBeVisible()
  await expect(page).toHaveURL(/\/jobs/) // back to the page that was asked for

  // Profile: upload a CV, review, save.
  await tool(page, 'CV')
  await page.getByLabel('CV file').setInputFiles(path.join(FIXTURES, 'cv_sample.pdf'))
  await page.getByRole('button', { name: 'Extract profile' }).click()
  await expect(page.getByLabel('Name', { exact: true })).not.toHaveValue('', { timeout: 120_000 })
  await page.getByLabel('Summary').fill('Edited in the journey.')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Profile saved.')).toBeVisible()

  // Home is the dashboard: it names the next step of the journey.
  await nav(page, 'Home').click()
  await expect(page.getByRole('region', { name: 'Next step' })).toContainText('Review your CV')
  if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/home.png` })

  // Coach: the chat streams a reply and shows up in the sidebar's Recent list.
  await page.goto('/chat') // the Agents page gets its Coach card in AP-06
  await page.getByRole('button', { name: 'Review my CV' }).click()
  await expect(page.getByText('Votre profil est solide.')).toBeVisible({ timeout: 60_000 })
  if (narrow(page)) await page.getByRole('button', { name: 'Open menu' }).click() // the sidebar is a drawer
  const recent = page.getByRole('navigation', { name: 'Recent' })
  await expect(recent).toContainText('Review my CV')
  if (narrow(page)) await recent.getByRole('link').first().click() // a link closes the drawer

  // Jobs: paste a description.
  await tool(page, 'Jobs')
  await page.getByLabel('Job description text').fill(JD)
  await page.getByRole('button', { name: 'Add job' }).click()
  await expect(page.getByText(/Job added:/)).toBeVisible({ timeout: 120_000 })

  // Fit report.
  await page.locator('button[aria-controls^="job-row-"]').first().click() // open the row
  await page.getByRole('link', { name: 'Check fit' }).first().click()
  await page.getByRole('button', { name: 'Analyse my fit' }).click()
  await expect(page.getByText(/\/100/)).toBeVisible({ timeout: 120_000 })

  // Letter: generate, edit a paragraph, run the quality check, export as text.
  await page.getByRole('link', { name: 'Write a cover letter' }).click()
  await page.getByRole('button', { name: 'Generate letter' }).click()
  const paragraph = page.getByLabel('Paragraph 1', { exact: true })
  await expect(paragraph).toBeVisible({ timeout: 120_000 })
  await paragraph.fill('Un paragraphe modifié.')
  await page.getByRole('button', { name: 'Save Paragraph 1' }).click()
  await expect(page.getByRole('button', { name: 'Save Paragraph 1' })).toBeDisabled()
  await page.getByRole('button', { name: 'Run check' }).click()
  await expect(page.getByText(/words \(target/)).toBeVisible({ timeout: 60_000 })
  const textDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download as text' }).click()
  expect((await textDownload).suggestedFilename()).toBe('letter.txt')
  if (process.env.E2E_RENDER) {
    // Needs a `tectonic` binary on the worker's PATH.
    await page.getByRole('button', { name: 'Render PDF' }).click()
    await expect(page.getByTitle('Letter PDF preview')).toBeVisible({ timeout: 120_000 })
  }

  // Helpers: an Interview prep helper tried on this job. Run says what is missing, then works.
  await nav(page, 'Agents').click()
  await page.getByRole('button', { name: 'New helper' }).click()
  await page
    .getByRole('button', { name: /Interview prep/ })
    .first()
    .click()
  const run = page.getByRole('button', { name: 'Run', exact: true })
  await expect(run).toBeDisabled()
  await expect(page.getByText('Pick a job to run it.')).toBeVisible()
  await page.locator('#try-job').selectOption({ index: 1 })
  await expect(run).toBeEnabled()
  await run.click()
  await expect(page.getByText('A canned item.').first()).toBeVisible({ timeout: 30_000 })

  // Tracker: add, move, see the timeline.
  await tool(page, 'Applications')
  await page.getByRole('button', { name: 'Track an application' }).first().click()
  await page.getByLabel('Company').fill('Fictiva Logiciels')
  await page.getByLabel('Status').selectOption('applied')
  await page.getByRole('button', { name: 'Add application' }).click()
  await page.getByLabel('Move Fictiva Logiciels').selectOption('interview')
  if (narrow(page)) await page.getByRole('tab', { name: /^Interview/ }).click() // one column at a time
  await expect(
    page.getByRole('region', { name: /Interview/ }).getByText('Fictiva Logiciels'),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Open Fictiva Logiciels' }).click()
  await page.getByLabel('Contact').fill('Marie Curie')
  await page.getByRole('button', { name: 'Save', exact: true }).click() // saves and closes the drawer
  await page.getByRole('button', { name: 'Open Fictiva Logiciels' }).click()
  await expect(page.getByLabel('Contact')).toHaveValue('Marie Curie')
  await page.getByRole('button', { name: 'Timeline' }).click()
  await expect(page.getByRole('list', { name: 'Timeline' })).toContainText('Interview')

  await page.keyboard.press('Escape') // close the drawer

  // Settings: export (worker task), then delete the account.
  if (narrow(page)) await page.getByRole('button', { name: 'Open menu' }).click()
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('menuitem', { name: 'Settings' }).click()
  await expect(page.getByText('How you sign in')).toBeVisible()
  await expect(page.getByText('Email and password connected')).toBeVisible()
  await page.getByRole('button', { name: 'Request export' }).click()
  await expect(page.getByRole('link', { name: /Download your export/ })).toBeVisible({
    timeout: 60_000,
  })
  await page.getByLabel(/Type DELETE/).fill('DELETE')
  await page.getByRole('button', { name: 'Delete my account' }).click()
  await expect(page).toHaveURL(/\/signin/)

  expect(problems).toEqual([])
  await expectNoA11yViolations(page)
})
