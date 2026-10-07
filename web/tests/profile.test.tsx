import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProfileForm } from '@/features/candidate/ProfileForm'
import { ProfilePage } from '@/features/candidate/ProfilePage'
import type { Profile } from '@/features/candidate/api'
import { toForm, toPatch } from '@/features/candidate/form'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), PATCH: vi.fn(), POST: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const profile = {
  id: 'p1',
  document_id: 'd1',
  schema_version: 2,
  updated_at: 't1',
  data: {
    personal_info: { name: 'Camille Test', email: null },
    formations: [],
    experiences: [
      {
        job_title: 'Dev',
        company: 'Acme',
        start_date: '2020-01',
        end_date: null,
        location: 'Lyon',
      },
    ],
    skills: [{ name: 'Python', category: null }],
    summary: null,
    references: [{ name: 'Prof. Durand', title: 'Professor', company: 'INSA Lyon' }],
  },
} as unknown as Profile

beforeEach(() => vi.clearAllMocks())

test('form mapping: nulls become empty inputs and back; unrendered fields survive', () => {
  const v = toForm(profile)
  expect(v.personal_info.email).toBe('')
  const patch = toPatch(v)
  expect(patch.personal_info?.email).toBeNull()
  expect(patch.summary).toBeNull()
  expect(patch.experiences?.[0]).toMatchObject({
    company: 'Acme',
    end_date: null,
    location: 'Lyon',
  })
})

test('save is blocked by validation, then PATCHes the edited profile', async () => {
  mocks.PATCH.mockResolvedValue({ data: profile })
  const user = userEvent.setup()
  renderWithApp(<ProfileForm profile={profile} />)
  await user.clear(screen.getByLabelText('Company (1)'))
  await user.click(screen.getByRole('button', { name: 'Save profile' }))
  expect(await screen.findByText('Job title and company are required.')).toBeInTheDocument()
  expect(mocks.PATCH).not.toHaveBeenCalled()

  await user.type(screen.getByLabelText('Company (1)'), 'Globex')
  await user.click(screen.getByRole('button', { name: 'Save profile' }))
  await waitFor(() => expect(mocks.PATCH).toHaveBeenCalled())
  expect(mocks.PATCH.mock.calls[0][1].body.experiences[0]).toMatchObject({
    company: 'Globex',
    location: 'Lyon',
  })
})

test('no profile (404) shows onboarding; API error shows message + request id', async () => {
  mocks.GET.mockResolvedValue({ response: { status: 404 } })
  const { unmount } = renderWithApp(<ProfilePage />)
  expect(await screen.findByText('Start with your CV')).toBeInTheDocument()
  unmount()

  mocks.GET.mockResolvedValue({
    error: { detail: 'The service is busy.', request_id: 'rq1' },
    response: { status: 503 },
  })
  renderWithApp(<ProfilePage />)
  expect(await screen.findByText(/The service is busy\. \(request id: rq1\)/)).toBeInTheDocument()
})

test('an existing profile is shown as blocks; Edit opens the form, saving returns to the view', async () => {
  mocks.GET.mockResolvedValue({ data: profile, response: { status: 200 } })
  mocks.PATCH.mockResolvedValue({ data: profile })
  const user = userEvent.setup()
  renderWithApp(<ProfilePage />)

  expect(await screen.findByText('Camille Test')).toBeInTheDocument()
  expect(screen.getByText('Python')).toBeInTheDocument()
  expect(screen.getByText('Prof. Durand')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save profile' })).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Edit profile' }))
  await user.click(await screen.findByRole('button', { name: 'Save profile' }))
  expect(await screen.findByRole('button', { name: 'Edit profile' })).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Update CV' }))
  expect(screen.getByText('Replace your CV')).toBeInTheDocument()
})
