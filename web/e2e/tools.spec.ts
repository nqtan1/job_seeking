import { expect, test } from '@playwright/test'
import { expectNoA11yViolations, places, signUp } from './support.ts'

test('tools: the Tools page lists the tools and one opens on its own page', async ({ page }) => {
  await signUp(page, 'tools')
  await places(page).getByRole('link', { name: 'Tools', exact: true }).click()
  const career = page.getByRole('region', { name: 'Career' })
  await expect(career.getByRole('link', { name: /^CV/ })).toBeVisible() // a career page
  await expect(career.getByRole('link', { name: /^Check my fit/ })).toBeVisible() // a registry tool

  // The search narrows the list; a card opens the tool's page.
  await page.getByRole('searchbox', { name: 'Search tools' }).fill('search jobs')
  await expect(career.getByRole('link', { name: /^Check my fit/ })).toHaveCount(0)
  await career.getByRole('link', { name: /^Search jobs/ }).click()
  await expect(page).toHaveURL(/\/tools\/job_search$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Search jobs' })).toBeVisible()
  await expect(page.getByText('Takes', { exact: true })).toBeVisible()
  await expect(page.getByText(/^query/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Use in a flow' })).toBeVisible()

  await expectNoA11yViolations(page)
})
