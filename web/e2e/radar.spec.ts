import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

// Needs the isolated stack with the scripted worker: backend/tests/e2e_stack.sh up
// (fit scores come out as 86, 38, 74 for the three offers; the minimum fit is 70).
const FIXTURES = path.resolve(import.meta.dirname, '../../backend/tests/fixtures')
const SHOTS = process.env.E2E_SHOTS

const menu = (page: Page, name: string | RegExp) =>
  page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name })

const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true })
}

test('radar: the user sees it work, understands the matches and follows one to the tracker', async ({
  page,
}) => {
  const problems: string[] = []
  page.on('pageerror', (e) => problems.push(e.message))
  await page.setViewportSize({ width: 1280, height: 900 })

  // A new user with a CV.
  await page.goto('/')
  await page.getByRole('button', { name: 'No account? Sign up' }).click()
  await page.getByLabel('Email').fill(`radar${Date.now()}@example.com`)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign up', exact: true }).click()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
  await menu(page, 'Profile').click()
  await page.getByLabel('CV file').setInputFiles(path.join(FIXTURES, 'cv_sample.pdf'))
  await page.getByRole('button', { name: 'Extract profile' }).click()
  await expect(page.getByLabel('Name', { exact: true })).not.toHaveValue('', { timeout: 120_000 })
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Profile saved.')).toBeVisible()

  // First visit: explained, with a one-click start taken from the CV.
  await menu(page, 'Radar').click()
  await expect(page.getByText('No radar yet')).toBeVisible()
  await expect(
    page.getByText(/It never applies for you and never contacts a company/),
  ).toBeVisible()
  await shot(page, '1-first-visit')
  await page.getByRole('button', { name: 'Start this radar' }).click()
  await expect(page.getByText(/fit ≥ 70%/)).toBeVisible()

  // The radar can be edited afterwards.
  await page.getByRole('button', { name: /^Edit / }).click()
  await page.getByRole('button', { name: /All France/ }).click()
  await page.getByRole('checkbox', { name: 'Paris (75)' }).click()
  await page.getByRole('checkbox', { name: 'Lyon · Rhône (69)' }).click()
  await shot(page, '0-places')
  await page.getByRole('button', { name: 'CDI', exact: true }).click()
  await page.getByRole('button', { name: 'CDD', exact: true }).click()
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(
    page.getByText(
      /Senior Python Engineer · Paris \(75\), Lyon · Rhône \(69\) · CDI,CDD · fit ≥ 70%/,
    ),
  ).toBeVisible()

  // Run now: the user watches it work, then sees what it found.
  await page.getByRole('button', { name: 'Run now' }).click()
  await expect(page.getByRole('button', { name: 'Searching…' })).toBeVisible()
  await shot(page, '2-running')
  const strip = page.getByRole('region', { name: 'Radar status' })
  await expect(strip.getByText(/looked at 3 new offers, kept 2/)).toBeVisible({ timeout: 60_000 })

  // Matches come with the reasons; the weak one is not hidden.
  const best = page.getByRole('listitem').filter({ hasText: 'Développeur Python Backend' })
  await expect(best.getByText('Fit 86%')).toBeVisible()
  await expect(best.getByText('Why it fits')).toBeVisible()
  await expect(best.getByText('Python and FastAPI experience')).toBeVisible()
  const second = page.getByRole('listitem').filter({ hasText: 'Data Engineer Python' })
  await expect(second.getByText('Fit 74%')).toBeVisible()
  await expect(second.getByText('Kubernetes')).toBeVisible() // what to watch
  await page.getByText(/Checked but not shortlisted \(1\)/).click()
  await expect(page.getByText(/Ingénieur Java Senior/)).toBeVisible()
  await expect(page.getByText(/missing: Kubernetes/)).toBeVisible()
  await expect(page.getByRole('region', { name: 'Your last 30 days' })).toContainText('Looked at 3')
  await expect(page.getByRole('region', { name: 'What your radar did' })).toContainText(
    'looked at 3 new, kept 2',
  )
  // The user is looking at the matches, so the "new" badge in the menu and the tab goes away
  // (the badge showing up for unseen matches is covered by tests/radar-badge.test.tsx).
  await expect(menu(page, /Radar/).getByLabel(/new matches/)).toHaveCount(0)
  await expect(page).toHaveTitle('RecruitAI')
  await shot(page, '3-results')

  // Keep the best one: it goes on to the letter, and the radar keeps following it.
  await page.getByRole('button', { name: 'Keep and write a letter' }).first().click()
  await expect(page).toHaveURL(/\/letters\?job=/)
  await menu(page, /Radar/).click()
  const following = page.getByRole('region', { name: 'Following up' })
  await expect(following.getByText('Développeur Python Backend')).toBeVisible()
  await following.getByRole('button', { name: 'I applied' }).click()
  await expect(following.getByText('Applied')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Your last 30 days' })).toContainText(
    'Applied to 1',
  )
  await shot(page, '4-following')

  // From there, the whole offer and its analysis are one click away.
  await following.getByRole('link', { name: 'Job & analysis' }).click()
  await expect(page).toHaveURL(/\/jobs\/.+\/fit/)
  await expect(page.getByText('Job description')).toBeVisible()
  await expect(page.getByText('Développeur Python Backend chez Fictiva Logiciels.')).toBeVisible()
  await expect(page.getByRole('link', { name: /View the original offer/ })).toHaveAttribute(
    'href',
    /candidat\.francetravail\.fr\/offres\/recherche\/detail\/E1/,
  )
  await shot(page, '8-job-and-analysis')
  await menu(page, /Radar/).click()

  // It shows in the tracker, and the jobs list says where it came from.
  await menu(page, 'Tracker').click()
  await expect(page.getByRole('region', { name: 'Applied' })).toContainText('Fictiva Logiciels')
  await menu(page, 'Jobs').click()
  await expect(page.getByText('From radar').first()).toBeVisible()
  await shot(page, '5-jobs')

  // Disagree with a rejection: review it anyway, with no new AI call.
  await menu(page, /Radar/).click()
  await page.getByText(/Checked but not shortlisted/).click()
  await page.getByRole('button', { name: 'Review Ingénieur Java Senior anyway' }).click()
  await expect(page).toHaveURL(/\/jobs\/.+\/fit/)
  await expect(page.getByRole('heading', { name: 'Ingénieur Java Senior' })).toBeVisible()
  await expect(page.getByText('Ingénieur Java Senior chez Corp Industries.')).toBeVisible()

  expect(problems).toEqual([])
})
