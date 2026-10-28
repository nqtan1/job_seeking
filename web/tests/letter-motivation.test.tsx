import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LettersPage } from '@/features/letters/LettersPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const QUESTIONS = [
  { question: "Qu'est-ce qui vous attire au CEA ?", hint: 'Un domaine précis' },
  { question: 'Un moment chez Alpha qui vous a marqué ?', hint: 'Un chiffre ou un blocage' },
  { question: 'Que voulez-vous apprendre ici ?', hint: 'Un sujet concret' },
]
const LONG = 'Mon grand-père était technicien à Cadarache, je veux servir la fusion.'

beforeEach(() => {
  vi.clearAllMocks()
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/jobs')
      return {
        data: [
          { id: 'j1', data: { title: 'Dev', company: { name: 'Acme' } } },
          { id: 'j2', data: { title: 'Data', company: { name: 'Beta' } } },
        ],
      }
    if (url === '/api/v1/fit-analyses')
      return { data: [{ id: 'f1', data: { strengths: ['Python depuis 5 ans', 'CI/CD'] } }] }
    return { data: [] }
  })
  mocks.POST.mockImplementation(async (url: string) =>
    url === '/api/v1/letters/motivation-questions'
      ? { data: { questions: QUESTIONS } }
      : { data: { id: 'l1', content: {} } },
  )
})

const open = async (user: ReturnType<typeof userEvent.setup>, job = 'j1') => {
  renderWithApp(<LettersPage />, { at: '/letters', path: '/letters' })
  await screen.findByRole('option', { name: /Dev/ }) // the jobs have loaded
  await user.selectOptions(screen.getByLabelText('Job'), job)
}

test('tailored questions, real answers and tapped strengths all go to the letter request', async () => {
  const user = userEvent.setup()
  await open(user)

  // With nothing answered, the form says plainly that the letter will stay factual.
  expect(screen.getByText(/No personal motivation yet/)).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Ask me 3 questions about this job' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/letters/motivation-questions', {
      body: { job_id: 'j1', language: 'en' },
    }),
  )
  await user.click(await screen.findByRole('button', { name: 'Python depuis 5 ans' }))
  await user.type(await screen.findByLabelText(/1\. Qu'est-ce qui vous attire/), LONG)
  expect(screen.getByText(/Answer at least two questions/)).toBeInTheDocument() // one is not enough
  await user.type(screen.getByLabelText(/2\. Un moment chez Alpha/), `${LONG} (à Alpha)`)
  expect(screen.queryByText(/Answer at least two questions/)).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Generate letter' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/letters', {
      body: expect.objectContaining({
        job_id: 'j1',
        highlights: ['Python depuis 5 ans'],
        // Only the answered questions are sent, each with its question.
        answers: [
          { question: QUESTIONS[0].question, answer: LONG },
          { question: QUESTIONS[1].question, answer: `${LONG} (à Alpha)` },
        ],
      }),
    }),
  )
})

test('switching job drops the questions and answers of the previous one', async () => {
  const user = userEvent.setup()
  await open(user)
  await user.click(screen.getByRole('button', { name: 'Ask me 3 questions about this job' }))
  await user.type(await screen.findByLabelText(/1\. Qu'est-ce qui vous attire/), LONG)

  await user.selectOptions(screen.getByLabelText('Job'), 'j2')
  expect(screen.queryByLabelText(/1\. Qu'est-ce qui vous attire/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Generate letter' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/letters', {
      body: expect.objectContaining({ job_id: 'j2', answers: [] }),
    }),
  )
})

test('"I write it myself" sends the own_words mode with the user\'s note', async () => {
  const user = userEvent.setup()
  await open(user)
  await user.click(screen.getByRole('radio', { name: /I write it myself/ }))
  await user.click(screen.getByRole('button', { name: 'Ask me 3 questions about this job' }))
  await user.type(await screen.findByLabelText(/Anything else, in your own words/), 'Mon texte')
  await user.click(screen.getByRole('button', { name: 'Create my letter with ideas' }))

  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/letters', {
      body: expect.objectContaining({ mode: 'own_words', motivation: 'Mon texte' }),
    }),
  )
})
