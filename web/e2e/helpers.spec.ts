import { expect, test, type Page } from '@playwright/test'

const nav = (page: Page, name: string) =>
  page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name, exact: true })

test('helpers: template → edit → try → two-step flow → run → inspect → replay', async ({
  page,
}) => {
  const problems: string[] = []
  page.on('pageerror', (e) => problems.push(e.message))

  await page.goto('/helpers')
  await page.getByRole('button', { name: 'No account? Sign up' }).click()
  await page.getByLabel('Email').fill(`helpers${Date.now()}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill('password123')
  await page.getByLabel('Confirm password').fill('password123')
  await page.getByRole('button', { name: 'Sign up', exact: true }).click()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
  await nav(page, 'Helpers').click()

  // A helper from a template opens in the editor with its own id and character.
  await expect(page.getByText('No helper yet')).toBeVisible()
  await page.getByRole('button', { name: 'Use this template' }).first().click()
  await expect(page.getByLabel('Instructions')).toContainText('follow-up')
  await expect(page.getByText(/^ID: /)).toBeVisible()

  // Edit, try it on unsaved text, then save a version.
  await page.getByLabel('Name', { exact: true }).fill('Mira')
  await page.getByLabel('Instructions').fill('Write a very short polite follow-up.')
  await page.locator('#try-notes').fill('Applied to Acme last Monday')
  await page.getByRole('button', { name: 'Run', exact: true }).click()
  await expect(page.getByText('A canned helper answer.')).toBeVisible()
  await page.getByRole('button', { name: /Save version/ }).click()
  await expect(page.getByText('Saved.')).toBeVisible()

  // A flow: Start → Mira → Result, built in the Steps view.
  await page.goto('/automations')
  await page.getByRole('button', { name: 'New automation' }).first().click()
  await page.getByLabel('Name').fill('Follow-up flow')
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await page.getByRole('button', { name: 'Steps', exact: true }).click()
  await page.getByLabel('Add a helper…').selectOption({ label: 'Mira' })
  await expect(page.getByRole('button', { name: 'Mira Helper' })).toBeVisible()
  // A just-added helper refuses links until its details have loaded ("still loading"): retry.
  await expect(async () => {
    await page.getByLabel('Send to…').first().selectOption({ label: 'Mira' }) // Start → Mira
    await expect(page.getByText('still loading')).toHaveCount(0, { timeout: 500 })
  }).toPass()
  await page.getByLabel('Send to…').nth(1).selectOption({ label: 'Result' }) // Mira → Result
  await expect(page.getByText('Ready to run')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Data between steps' })).toContainText('notes')

  // What moves from Start to Mira is visible, with the previews rendered by the server.
  await page.getByRole('button', { name: '→ Mira', exact: true }).click()
  await expect(page.getByText('The next step cannot see:')).toBeVisible()
  await expect(page.getByText('What this step gives back')).toBeVisible() // with an example each

  await expect(page.getByRole('button', { name: 'Run flow' })).toBeDisabled() // unsaved
  await page.getByRole('button', { name: /Save version/ }).click()
  await expect(page.getByText('Saved.')).toBeVisible()
  await page.getByRole('button', { name: 'Run flow' }).click()
  await page.getByLabel('Your text').fill('Applied to Acme last Monday')
  await expect(page.getByText(/Uses up to 1 of your/)).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: 'Watch it run' }).click()

  // The run happens in place: the editor stays, the canvas lights up, the result appears beside it.
  await expect(page).toHaveURL(/\/automations\//)
  const live = page.getByRole('region', { name: 'Live run' })
  await expect(live.getByText('Done', { exact: true }).first()).toBeVisible({ timeout: 60_000 })
  await expect(live.getByRole('region', { name: 'Result' })).toContainText(
    'A canned helper answer.',
  )
  await expect(live.getByText(/Finished in/)).toBeVisible()

  // Run again follows the new run in place; the full page keeps the replay and the data between steps.
  await live.getByRole('button', { name: 'Run again' }).click()
  await expect(live.getByText('Done', { exact: true }).first()).toBeVisible({ timeout: 60_000 })
  await live.getByRole('link', { name: 'Open full page' }).click()
  await expect(page).toHaveURL(/\/automations\/runs\//)
  await expect(page.getByText('Done', { exact: true }).first()).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('region', { name: 'Result' })).toContainText(
    'A canned helper answer.',
  )
  await page.getByRole('button', { name: 'Steps', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Data between steps' })).toContainText('characters')
  await page.getByRole('button', { name: 'Replay' }).click()
  await expect(page.getByRole('slider', { name: 'Replay' })).toBeVisible()

  // The Runs page lists both runs; filters work and "Run again" opens a new run.
  await page.goto('/automations?tab=runs')
  await expect(page.getByRole('list', { name: 'Your runs' }).getByRole('listitem')).toHaveCount(2)
  await page.getByRole('button', { name: 'Failed' }).click()
  await expect(page.getByText('No run matches this filter')).toBeVisible()
  await page.getByRole('button', { name: 'Done' }).click()
  await expect(page.getByRole('list', { name: 'Your runs' }).getByRole('listitem')).toHaveCount(2)

  // A schedule: pick "every day", it is saved and can be paused.
  await page.goto('/automations')
  await page
    .getByRole('link', { name: /Follow-up flow/ })
    .first()
    .click()
  const sched = page.locator('section', {
    has: page.getByRole('heading', { name: 'Run it by itself' }),
  })
  await sched.getByRole('button', { name: 'Add a schedule' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByText('Every day', { exact: true }).click()
  await dialog.getByLabel('Your text').fill('Daily check')
  await dialog.getByRole('button', { name: 'Add this schedule' }).click()
  await expect(sched.getByText(/Every day at/)).toBeVisible()
  await sched.getByRole('button', { name: /^Pause/ }).click()
  await expect(sched.getByRole('button', { name: /^Resume/ })).toBeVisible()

  // A ready-made automation creates its helpers and the flow in one click.
  await page.goto('/automations')
  await page.getByRole('button', { name: 'Create this automation' }).first().click()
  await expect(page).toHaveURL(/\/automations\//, { timeout: 30_000 })
  await expect(page.getByText('Ready to run')).toBeVisible()

  // Action blocks: add "Search jobs"; it appears as a step that still needs its input wired.
  await page.getByLabel('Add an action…').selectOption({ label: 'Search jobs' })
  await expect(page.getByRole('button', { name: /Search jobs/ }).first()).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: /to fix/ })).toBeVisible()
  // Selecting it shows what it gives back, with an example, so links can be wired by looking.
  await page
    .getByRole('button', { name: /Search jobs/ })
    .first()
    .click()
  await expect(page.getByText('What this step gives back')).toBeVisible()
  await expect(page.getByText('{{count}}')).toBeVisible()
  await page.screenshot({
    path: process.env.SHOTS ? `${process.env.SHOTS}/outputs.png` : undefined,
  })

  // "Start an automation for each" needs its target: the checks say so until one is chosen.
  await page.getByLabel('Add an action…').selectOption({ label: 'Start an automation for each' })
  await expect(page.getByText('Choose the automation to start.')).toBeVisible({ timeout: 15_000 })

  // Contacts: add someone to email; they stay "waiting for their OK" until they confirm.
  await page.goto('/automations?tab=contacts')
  await expect(page.getByText('You have not added anyone yet.')).toBeVisible()
  // a new address each run: a real address may only be mailed 3 times a day
  await page.getByLabel('Add a contact').fill(`friend-${Date.now()}@example.com`)
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(page.getByText('Waiting for their OK')).toBeVisible({ timeout: 15_000 })
  await page.screenshot({
    path: process.env.SHOTS ? `${process.env.SHOTS}/contacts.png` : undefined,
  })

  expect(problems).toEqual([])
})
