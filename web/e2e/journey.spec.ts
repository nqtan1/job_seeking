import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// Synthetic fixtures only.
const FIXTURES = path.resolve(import.meta.dirname, '../../backend/tests/fixtures')
const JD = fs.readFileSync(path.join(FIXTURES, 'live/jd_python_paris.txt'), 'utf8')

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
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign up', exact: true }).click()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
  await expect(page).toHaveURL(/\/jobs/) // back to the page that was asked for

  // Profile: upload a CV, review, save.
  await page.getByRole('link', { name: 'Profile' }).click()
  await page.getByLabel('CV file').setInputFiles(path.join(FIXTURES, 'cv_sample.pdf'))
  await page.getByRole('button', { name: 'Extract profile' }).click()
  await expect(page.getByLabel('Name', { exact: true })).not.toHaveValue('', { timeout: 120_000 })
  await page.getByLabel('Summary').fill('Edited in the journey.')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Profile saved.')).toBeVisible()

  // Coach: the home chat streams a reply and shows up in the sidebar's Recent list.
  await page.getByRole('link', { name: 'New chat' }).click()
  await page.getByRole('button', { name: 'Review my CV' }).click()
  await expect(page.getByText('Votre profil est solide.')).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('region', { name: 'Recent chats' })).toContainText('Review my CV')

  // Jobs: paste a description.
  await page.getByRole('link', { name: 'Jobs' }).click()
  await page.getByLabel('Job description text').fill(JD)
  await page.getByRole('button', { name: 'Add job' }).click()
  await expect(page.getByText(/Job added:/)).toBeVisible({ timeout: 120_000 })

  // Fit report.
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

  // Tracker: add, move, see the timeline.
  await page.getByRole('link', { name: 'Tracker' }).click()
  await page.getByLabel('Company').fill('Fictiva Logiciels')
  await page.getByLabel('Status').selectOption('applied')
  await page.getByRole('button', { name: 'Add application' }).click()
  await page.getByLabel('Move Fictiva Logiciels').selectOption('interview')
  await expect(
    page.getByRole('region', { name: /Interview/ }).getByText('Fictiva Logiciels'),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Details' }).click()
  await page.getByLabel('Contact').fill('Marie Curie')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByText('Contact: Marie Curie')).toBeVisible()
  await page.getByRole('button', { name: 'Timeline' }).click()
  await expect(page.getByRole('list', { name: 'Timeline' })).toContainText('Interview')

  // Settings: export (worker task), then delete the account.
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('menuitem', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'Request export' }).click()
  await expect(page.getByRole('link', { name: /Download your export/ })).toBeVisible({
    timeout: 60_000,
  })
  await page.getByLabel(/Type DELETE/).fill('DELETE')
  await page.getByRole('button', { name: 'Delete my account' }).click()
  await expect(page).toHaveURL(/\/signin/)

  expect(problems).toEqual([])
})
