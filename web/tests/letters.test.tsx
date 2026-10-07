import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LetterPage } from '@/features/letters/LetterPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const base = {
  id: 'l1',
  render_status: 'none',
  pdf_document_id: null,
  content: {
    subject: 'Application',
    salutation: 'Hello',
    opening: 'Hi',
    body: ['P one', 'P two'],
    closing: 'Bye',
  },
}

const renderPage = () =>
  renderWithApp(<LetterPage />, { at: '/letters/l1', path: '/letters/:letterId' })

let letter: Omit<typeof base, 'pdf_document_id'> & { pdf_document_id: string | null }
beforeEach(() => {
  vi.clearAllMocks()
  letter = { ...base }
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/letters/{letter_id}') return { data: letter }
    if (url === '/api/v1/tasks/{task_id}') return { data: { status: 'done' } }
    if (url.endsWith('/versions')) return { data: [] }
    return { data: { download_url: '/pdf/l1.pdf' } } // PDF link
  })
})

test('editing one paragraph enables only its Save, which PATCHes that paragraph index', async () => {
  const user = userEvent.setup()
  mocks.PATCH.mockResolvedValue({
    data: { ...letter, content: { ...letter.content, body: ['P one', 'P two edited'] } },
  })
  renderPage()
  const save2 = await screen.findByRole('button', { name: 'Save Paragraph 2' })
  expect(save2).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Save Paragraph 1' })).toBeDisabled()

  await user.type(screen.getByLabelText('Paragraph 2'), ' edited')
  expect(screen.getByRole('button', { name: 'Save Paragraph 1' })).toBeDisabled()
  await user.click(save2)
  await waitFor(() =>
    expect(mocks.PATCH).toHaveBeenCalledWith('/api/v1/letters/{letter_id}/blocks/{block}', {
      params: { path: { letter_id: 'l1', block: 'body' } },
      body: { text: 'P two edited', index: 1 },
    }),
  )
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Save Paragraph 2' })).toBeDisabled(),
  )
})

test('render: queued task is polled until done, then the PDF preview appears', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValue({ data: { task_id: 't1', status_url: '/x' } })
  let polls = 0
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/letters/{letter_id}') return { data: letter }
    if (url === '/api/v1/tasks/{task_id}') {
      polls++
      if (polls > 1) letter = { ...letter, pdf_document_id: 'd1' }
      return { data: { status: polls > 1 ? 'done' : 'queued' } }
    }
    if (url.endsWith('/versions')) return { data: [] }
    return { data: { download_url: '/pdf/l1.pdf' } }
  })
  renderPage()
  await user.click(await screen.findByRole('button', { name: 'Render PDF' }))
  expect(await screen.findByRole('button', { name: 'Rendering PDF…' })).toBeInTheDocument()
  const frame = await screen.findByTitle('Letter PDF preview', {}, { timeout: 6000 })
  expect(frame).toHaveAttribute('src', '/pdf/l1.pdf')
  expect(polls).toBeGreaterThan(1)
}, 15000)
