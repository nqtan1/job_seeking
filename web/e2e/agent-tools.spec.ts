import { expect, test } from '@playwright/test'
import { expectNoA11yViolations, places, signUp } from './support.ts'

test('Studio › Tools: try an agent tool for real in the side panel', async ({ page }) => {
  await signUp(page, 'tools')
  await places(page).getByRole('link', { name: 'Studio', exact: true }).click()
  await page
    .getByRole('navigation', { name: 'Section' })
    .getByRole('link', { name: 'Tools', exact: true })
    .click()
  await expect(page.getByText('Running inside the app')).toBeVisible() // no tools service in e2e

  await page.getByRole('button', { name: 'Try Save a note' }).click()
  const panel = page.getByRole('dialog', { name: 'Save a note' })
  await panel.getByLabel('Note title').fill('Lyon offers')
  await panel.getByLabel('Note text').fill('Three to read this week.')
  await expectNoA11yViolations(page)
  await panel.getByRole('button', { name: 'Run', exact: true }).click()
  await expect(panel.getByText(/ms inside the app/)).toBeVisible({ timeout: 30_000 })
  await expect(panel.getByRole('heading', { name: 'Result' })).toBeVisible()

  await panel.getByRole('button', { name: 'Close' }).click()
  await expect(panel).toBeHidden()
})
