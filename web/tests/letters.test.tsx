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
    recipient: {},
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

test('a letter written by the user shows ideas beside its blocks and waits for every paragraph', async () => {
  letter = {
    ...base,
    content: { ...base.content, opening: '', body: ['Mes mots', ''] },
    ideas: {
      opening: ['Parler de Zarr'],
      body: [null, { requirement: 'Tests', proof: 'CI 40 → 8 min', angle: 'Chiffrer' }],
      closing: ['Proposer un entretien'],
    },
  } as unknown as typeof letter
  renderPage()
  expect(await screen.findByText('Parler de Zarr')).toBeInTheDocument()
  expect(screen.getByText('Answer: Tests')).toBeInTheDocument()
  expect(screen.getByText('Proposer un entretien')).toBeInTheDocument()
  // The paragraph that already holds their words gets no idea box; the PDF waits.
  expect(screen.getAllByText('Ideas')).toHaveLength(3)
  expect(screen.getByRole('button', { name: 'Render PDF' })).toBeDisabled()
})

const issue = (key: string, start: number, wrong: string, right: string) => ({
  key,
  start,
  end: start + wrong.length,
  wrong,
  right,
  reason: 'accent',
})

test('spelling: check one paragraph, apply a correction into the draft, then save it', async () => {
  const user = userEvent.setup()
  letter = { ...base, content: { ...base.content, body: ['Une opportunitée unique', 'P two'] } }
  mocks.POST.mockResolvedValue({
    data: { checked: 1, issues: [issue('body.0', 4, 'opportunitée', 'opportunité')] },
  })
  renderPage()
  await user.click(await screen.findByRole('button', { name: 'Check spelling of Paragraph 1' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/letters/{letter_id}/spellcheck', {
      params: { path: { letter_id: 'l1' } },
      body: { items: [{ key: 'body.0', text: 'Une opportunitée unique' }] },
    }),
  )
  // Nothing changes until the user accepts, and the correction is shown in its context.
  expect(screen.getByLabelText('Paragraph 1')).toHaveValue('Une opportunitée unique')
  await user.click(await screen.findByRole('button', { name: /Apply 1 of 1: opportunitée/ }))
  expect(screen.getByLabelText('Paragraph 1')).toHaveValue('Une opportunité unique')
  expect(screen.getByRole('button', { name: 'Save Paragraph 1' })).toBeEnabled()
  // The unsaved state is spelled out, not "no issue found".
  expect(
    screen.getByText('Corrections applied. Save this paragraph to keep them.'),
  ).toBeInTheDocument()
})

test('spelling: editing a checked paragraph says so instead of silently dropping the result', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValue({ data: { checked: 4, issues: [] } })
  renderPage()
  await user.click(
    await screen.findByRole('button', { name: 'Check spelling of the whole letter' }),
  )
  expect(await screen.findAllByText('No spelling or grammar issue found.')).not.toHaveLength(0)

  await user.type(screen.getByLabelText('Opening'), '!')
  expect(
    await screen.findByText(/You edited this paragraph since the last check/),
  ).toBeInTheDocument()
})

test('spelling: a partial check is not reported as the whole letter being clean', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValue({ data: { checked: 1, issues: [] } })
  renderPage()
  await user.click(await screen.findByRole('button', { name: 'Check spelling of Opening' }))
  expect(await screen.findByText(/Checked 1 of 6 paragraphs/)).toBeInTheDocument()
})

test('spelling: ignoring is remembered in the message, and several corrected paragraphs save at once', async () => {
  const user = userEvent.setup()
  letter = {
    ...base,
    content: { ...base.content, opening: 'Un erreure', body: ['Une autre erreure', 'P two'] },
  }
  mocks.POST.mockResolvedValue({
    data: {
      checked: 5,
      issues: [issue('opening', 3, 'erreure', 'erreur'), issue('body.0', 10, 'erreure', 'erreur')],
    },
  })
  mocks.PATCH.mockImplementation(async () => ({ data: letter }))
  renderPage()
  await user.click(
    await screen.findByRole('button', { name: 'Check spelling of the whole letter' }),
  )
  await user.click(await screen.findByRole('button', { name: 'Apply all 2 corrections' }))
  expect(screen.getByLabelText('Opening')).toHaveValue('Un erreur')
  expect(screen.getByLabelText('Paragraph 1')).toHaveValue('Une autre erreur')

  await user.click(screen.getByRole('button', { name: 'Save 2 changes' }))
  await waitFor(() => expect(mocks.PATCH).toHaveBeenCalledTimes(2))
  expect(mocks.PATCH).toHaveBeenCalledWith('/api/v1/letters/{letter_id}/blocks/{block}', {
    params: { path: { letter_id: 'l1', block: 'opening' } },
    body: { text: 'Un erreur', index: null },
  })
})

test('spelling: ignoring the last correction says it was ignored, not that none was found', async () => {
  const user = userEvent.setup()
  letter = { ...base, content: { ...base.content, opening: 'Un erreure' } }
  mocks.POST.mockResolvedValue({
    data: { checked: 1, issues: [issue('opening', 3, 'erreure', 'erreur')] },
  })
  renderPage()
  await user.click(await screen.findByRole('button', { name: 'Check spelling of Opening' }))
  await user.click(await screen.findByRole('button', { name: /Ignore 1 of 1/ }))
  expect(await screen.findByText('No more corrections (1 ignored).')).toBeInTheDocument()
  expect(screen.getByLabelText('Opening')).toHaveValue('Un erreure') // untouched
})

test('spelling: the whole-letter button waits for something to check', async () => {
  letter = {
    ...base,
    content: { subject: '', salutation: '', opening: '', body: [''], closing: '', recipient: {} },
  }
  renderPage()
  expect(
    await screen.findByRole('button', { name: 'Check spelling of the whole letter' }),
  ).toBeDisabled()
})

test('an empty recipient shows the hint; saving PATCHes it and the letter is updated from the response', async () => {
  const user = userEvent.setup()
  mocks.PATCH.mockResolvedValue({
    data: { ...letter, content: { ...letter.content, recipient: { company: 'Acme' } } },
  })
  renderPage()
  expect(await screen.findByText(/Not found in the posting/)).toBeInTheDocument()
  await user.type(screen.getByLabelText('Company'), 'Acme')
  await user.click(screen.getByRole('button', { name: 'Save recipient' }))
  await waitFor(() =>
    expect(mocks.PATCH).toHaveBeenCalledWith('/api/v1/letters/{letter_id}/recipient', {
      params: { path: { letter_id: 'l1' } },
      body: { company: 'Acme', contact_name: '', address: '' },
    }),
  )
  await waitFor(() => expect(screen.queryByText(/Not found in the posting/)).toBeNull())
})
