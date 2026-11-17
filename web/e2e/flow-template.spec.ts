import { expect, test } from '@playwright/test'
import { expectNoA11yViolations, places, signUp } from './support.ts'

test('flow template: install a ready-made flow, run it, the run finishes', async ({ page }) => {
  await signUp(page, 'flow')
  await places(page).getByRole('link', { name: 'Flows', exact: true }).click()
  await page.getByRole('button', { name: 'Use: Follow up after applying' }).click()
  await expect(page).toHaveURL(/\/automations\/[0-9a-f-]{36}/, { timeout: 30_000 })
  await expect(page.getByText('Ready', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Run flow' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox').first().fill('Acme, backend developer, applied last Monday')
  await dialog.getByRole('button', { name: 'Watch it run' }).click()

  const live = page.getByRole('region', { name: 'Live run' })
  await expect(live.getByText('Done', { exact: true }).first()).toBeVisible({ timeout: 60_000 })
  // the scripted worker's helper answer (backend/tests/e2e_worker.py)
  await expect(live.getByRole('region', { name: 'Result' })).toContainText(
    'A canned helper answer.',
  )

  await expectNoA11yViolations(page)
})
