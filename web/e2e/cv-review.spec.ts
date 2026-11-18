import { expect, test } from '@playwright/test'
import path from 'node:path'
import { FIXTURES, career, expectNoA11yViolations, narrow, signUp } from './support.ts'

// The scripted worker comments every CV line, quoting its first words (backend/tests/e2e_worker.py).
test('cv review: upload a PDF, run the review, a comment highlights its passage on the PDF', async ({
  page,
}) => {
  await signUp(page, 'cvr')
  await career(page, 'CV')
  await page
    .getByRole('navigation', { name: 'Section' })
    .getByRole('link', { name: 'Review' })
    .click()

  await page
    .getByLabel('Upload a CV (PDF or DOCX)')
    .setInputFiles(path.join(FIXTURES, 'cv_sample.pdf'))
  await expect(page.getByLabel('Your CV')).not.toHaveValue('') // the upload is picked
  await page.getByRole('button', { name: 'Review my CV' }).click()
  await expect(page).toHaveURL(/\/cv-review\/[0-9a-f-]{36}/, { timeout: 60_000 })

  // A phone shows one column at a time: comments, then the CV.
  if (narrow(page)) await page.getByRole('tab', { name: 'Comments' }).click()
  await page
    .getByRole('region', { name: 'Comments' })
    .getByRole('button', { name: /Senior Python Engineer/ })
    .click()
  if (narrow(page)) await page.getByRole('tab', { name: 'CV' }).click()
  const cv = page.getByRole('region', { name: 'Your CV' })
  await expect(cv.getByRole('button', { name: 'Original PDF' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  // the cited passage, marked on the PDF page (the block overlays carry data-cvr-block)
  await expect(cv.locator('[data-cvr-focus]:not([data-cvr-block])').first()).toBeVisible()

  await expectNoA11yViolations(page)
})
