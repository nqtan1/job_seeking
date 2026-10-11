import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LettersPage } from '@/features/letters/LettersPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/jobs')
      return { data: [{ id: 'j1', data: { title: 'Dev', company: { name: 'Acme' } } }] }
    if (url === '/api/v1/fit-analyses')
      return { data: [{ id: 'f1', data: { strengths: ['Python depuis 5 ans', 'CI/CD'] } }] }
    return { data: [] }
  })
  mocks.POST.mockResolvedValue({ data: { id: 'l1', content: {} } })
})

test('the candidate taps strengths and writes their motivation; both go to the letter request', async () => {
  const user = userEvent.setup()
  renderWithApp(<LettersPage />, { at: '/letters', path: '/letters' })
  await screen.findByRole('option', { name: /Dev/ }) // the jobs have loaded
  await user.selectOptions(screen.getByLabelText('Job'), 'j1')

  const chip = await screen.findByRole('button', { name: 'Python depuis 5 ans' })
  expect(chip).toHaveAttribute('aria-pressed', 'false')
  await user.click(chip)
  expect(chip).toHaveAttribute('aria-pressed', 'true')

  await user.type(
    screen.getByLabelText('Your motivation, in your own words'),
    "J'aime leur mission",
  )
  await user.click(screen.getByRole('button', { name: 'Generate letter' }))

  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/letters', {
      body: expect.objectContaining({
        job_id: 'j1',
        highlights: ['Python depuis 5 ans'],
        motivation: "J'aime leur mission",
      }),
    }),
  )
})

test('"I write it myself" sends the own_words mode with the user\'s text', async () => {
  const user = userEvent.setup()
  renderWithApp(<LettersPage />, { at: '/letters', path: '/letters' })
  await screen.findByRole('option', { name: /Dev/ })
  await user.selectOptions(screen.getByLabelText('Job'), 'j1')
  await user.click(screen.getByRole('radio', { name: /I write it myself/ }))
  await user.type(screen.getByLabelText(/Your own words/), 'Mon texte')
  await user.click(screen.getByRole('button', { name: 'Create my letter with ideas' }))

  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/letters', {
      body: expect.objectContaining({ mode: 'own_words', motivation: 'Mon texte' }),
    }),
  )
})
