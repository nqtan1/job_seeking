import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LetterPage } from '@/features/letters/LetterPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const content = (opening: string) => ({
  subject: 'S',
  salutation: 'Hi',
  opening,
  body: ['P one'],
  closing: 'Bye',
})
const letter = (opening = 'I am very excited about this job') => ({
  id: 'l1',
  render_status: 'none',
  pdf_document_id: null,
  content: content(opening),
})

const renderPage = () =>
  renderWithApp(<LetterPage />, { at: '/letters/l1', path: '/letters/:letterId' })

beforeEach(() => {
  vi.clearAllMocks()
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/letters/{letter_id}') return { data: letter() }
    if (url === '/api/v1/letters/{letter_id}/versions')
      return {
        data: [{ n: 1, created_at: '2026-10-04T10:00:00Z', content: content('An older opening') }],
      }
    if (url === '/api/v1/letters/{letter_id}/check')
      return {
        data: {
          unsupported_claims: [
            { term: 'Kubernetes', kind: 'skill', sentence: 'I run Kubernetes.' },
          ],
          quality: {
            word_count: 180,
            target_words: 250,
            within_target: false,
            cliches: [],
            keyword_coverage: { covered: ['Python'], missing: ['Docker'] },
          },
        },
      }
    return { data: {} }
  })
})

test('selected text → AI action → suggestion replaces only the selection (unsaved until Save)', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValue({ data: { suggestion: 'keen' } })
  renderPage()
  const opening = (await screen.findByLabelText('Opening')) as HTMLTextAreaElement
  expect(screen.queryByRole('group', { name: /AI actions/ })).not.toBeInTheDocument()

  opening.setSelectionRange(5, 15) // "very excit"
  fireEvent.select(opening)
  await user.click(await screen.findByRole('button', { name: 'Shorten' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/letters/{letter_id}/assist', {
      params: { path: { letter_id: 'l1' } },
      body: { block: 'opening', selection: 'very excit', action: 'shorten' },
    }),
  )
  await user.click(await screen.findByRole('button', { name: 'Use suggestion' }))
  expect(opening.value).toBe('I am keened about this job')
  expect(screen.getByRole('button', { name: 'Save Opening' })).toBeEnabled()
  expect(mocks.PATCH).not.toHaveBeenCalled()
})

test('quality check shows unsupported claims and keyword gaps; versions can be restored', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValue({ data: letter('An older opening') })
  renderPage()
  await user.click(await screen.findByRole('button', { name: 'Run check' }))
  expect(await screen.findByText('Kubernetes')).toBeInTheDocument()
  expect(screen.getByText(/missing: Docker/)).toBeInTheDocument()
  expect(screen.getByText(/180 words/)).toBeInTheDocument()

  await user.type(screen.getByLabelText('Subject'), ' edited')
  await user.click(await screen.findByRole('button', { name: 'Restore version 1' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/letters/{letter_id}/versions/{n}/restore', {
      params: { path: { letter_id: 'l1', n: 1 } },
    }),
  )
  await waitFor(() => expect(screen.getByLabelText<HTMLTextAreaElement>('Subject').value).toBe('S'))
})

test('export downloads the text of the chosen format', async () => {
  const user = userEvent.setup()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  mocks.GET.mockImplementation(async (url: string) =>
    url.endsWith('/export')
      ? { data: { format: 'email', subject: 'Hello', body: 'Body text' } }
      : { data: url.endsWith('{letter_id}') ? letter() : [] },
  )
  renderPage()
  await user.click(await screen.findByRole('button', { name: 'Download as email' }))
  await waitFor(() => expect(click).toHaveBeenCalled())
  expect(mocks.GET).toHaveBeenCalledWith('/api/v1/letters/{letter_id}/export', {
    params: { path: { letter_id: 'l1' }, query: { format: 'email' } },
  })
})
