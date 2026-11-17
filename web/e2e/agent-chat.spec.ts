import { expect, test } from '@playwright/test'
import { expectNoA11yViolations, places, saveProfileFromCv, signUp } from './support.ts'

test('agent chat: from the Agents page, chat with a helper and get a reply', async ({ page }) => {
  await signUp(page, 'chat')
  await saveProfileFromCv(page) // a chat needs a profile

  // A helper from a template, then back to the Agents page.
  await places(page).getByRole('link', { name: 'Agents', exact: true }).click()
  await page.getByRole('button', { name: 'Use: Follow-up writer' }).click()
  await expect(page).toHaveURL(/\/helpers\/[0-9a-f-]{36}/)
  await page.goto('/helpers')

  await page.getByRole('link', { name: 'Chat: Follow-up writer' }).click()
  await expect(page).toHaveURL(/\/chat\?agent=/)
  await page.getByLabel('Message', { exact: true }).fill('Draft a follow-up for Acme.')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  // the fake model's streamed reply (backend/tests/e2e_server.py)
  await expect(page.getByText('Votre profil est solide.')).toBeVisible({ timeout: 60_000 })
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}/) // the chat is stored

  await expectNoA11yViolations(page)
})
