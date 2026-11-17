import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { CvReviewPage } from '@/features/cv-review/CvReviewPage'
import { setLang } from '@/i18n'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), DELETE: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const review = {
  id: 'r1',
  document_id: 'd1',
  parent_id: null,
  track: 'backend',
  level: 'mid',
  score: 61.2,
  created_at: '2026-11-12T10:00:00Z',
  data: {
    blocks: [
      { id: 'b1', kind: 'heading', section: 'experience', text: 'Experience' },
      { id: 'b2', kind: 'bullet', section: 'experience', text: 'Worked on the API' },
    ],
    comments: [
      {
        block_id: 'b2',
        criterion: 'impact.metric',
        citations: [{ block_id: 'b2', quote: 'Worked on' }],
        rating: 'poor',
        why: 'Describes a duty, no outcome.',
        improve: 'State the result.',
        rewrite: 'Cut API latency by [X%]',
        source: 'ai',
      },
      {
        block_id: 'b1',
        criterion: 'structure.format',
        citations: [],
        rating: 'moderate',
        why: 'Heading is vague.',
        improve: null,
        rewrite: null,
        source: 'rule',
      },
    ],
    dimensions: {
      impact: { score: 40, weight: 20, block_ids: ['b2'] },
      scope: { score: 50, weight: 15, reason: 'Small scope.', block_ids: [] },
    },
    summary: { strengths: [{ text: 'Clear stack', block_id: 'b1' }], top_fixes: ['b2'] },
    pages: 1,
    truncated: false,
    grounding_rate: 1,
  },
}

const renderPage = (at = '/cv-review/r1') =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <RouterProvider
        router={createMemoryRouter([{ path: '/cv-review/:reviewId?', element: <CvReviewPage /> }], {
          initialEntries: [at],
        })}
      />
    </QueryClientProvider>,
  )

beforeEach(() => {
  vi.clearAllMocks()
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/cv-reviews/{review_id}'
      ? { data: review }
      : url.endsWith('/layout')
        ? { error: { code: 'cv_no_pdf' } } // a text upload: no PDF view
        : { data: [] },
  )
  mocks.POST.mockResolvedValue({
    data: {
      signals: { b2: ['no_metric'] },
      dimensions: { impact: 55 },
      score: 70,
    },
  })
})

test('selecting a comment marks its quote; Use rewrite makes the evidence outdated; Undo restores it', async () => {
  const user = userEvent.setup()
  renderPage()
  const box = await screen.findByLabelText('CV text, line 2')
  expect(box).toHaveValue('Worked on the API')
  const card = screen.getByText(/Describes a duty/).closest('article')!
  expect(within(card).getByText('Weak')).toBeInTheDocument()
  expect(await within(card).findByText('No metric')).toBeInTheDocument() // baseline recheck chips

  expect(screen.getByText('No quote')).toBeInTheDocument() // the rule comment cites nothing
  expect(screen.getByText('Automatic check')).toBeInTheDocument()

  await user.click(box)
  expect(card).toHaveClass('ring-2') // the block now cites itself: the textarea must stay editable
  expect(box).toBeInTheDocument()
  expect(box).toHaveFocus()
  await user.click(screen.getByLabelText('CV text, line 1'))
  expect(card).not.toHaveClass('ring-2')
  await user.click(within(card).getByRole('button', { name: /Worked on the API/ }))
  const read = screen.getByLabelText('CV text, line 2')
  expect(read.querySelector('mark')).toHaveTextContent('Worked on')
  expect(read.closest('div')).toHaveClass('ring-2')
  expect(within(card).queryByText(/outdated/)).not.toBeInTheDocument()

  mocks.POST.mockClear()
  await user.click(screen.getByRole('button', { name: 'Use rewrite' }))
  expect(screen.getByLabelText('CV text, line 2')).toHaveValue('Cut API latency by [X%]')
  expect(within(card).getByText(/outdated/)).toBeInTheDocument()
  expect(screen.getByText(/Edited/)).toBeInTheDocument()
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith(
      '/api/v1/cv-reviews/recheck',
      expect.objectContaining({
        body: expect.objectContaining({
          blocks: expect.arrayContaining([
            expect.objectContaining({ id: 'b2', text: 'Cut API latency by [X%]' }),
          ]),
        }),
      }),
    ),
  )
  expect(await screen.findByText(/Live score.*: 70/)).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Undo' }))
  expect(screen.getByLabelText('CV text, line 2')).toHaveTextContent('Worked on the API')
  expect(within(card).queryByText(/outdated/)).not.toBeInTheDocument()
})

test('the criterion panel shows title, weight and source; a dimension jump selects its block', async () => {
  const user = userEvent.setup()
  renderPage()
  const card = (await screen.findByText(/Describes a duty/)).closest('article')!
  await user.click(within(card).getByText('Based on: Measurable result'))
  expect(within(card).getByText('weight 20%')).toBeInTheDocument()
  const link = within(card).getByRole('link', { name: 'Google XYZ formula' })
  expect(link).toHaveAttribute('href', expect.stringContaining('inc.com'))
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')

  const dims = screen.getByRole('region', { name: 'Dimensions' })
  expect(within(dims).getByText('Small scope.')).toBeInTheDocument() // model-scored reason
  expect(card).not.toHaveClass('ring-2')
  await user.click(within(dims).getByRole('button', { name: 'Line 2' }))
  expect(card).toHaveClass('ring-2')
})

test('a backend error code shows its translated message', async () => {
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/documents'
      ? {
          data: [
            {
              document_id: 'd1',
              kind: 'cv',
              mime: 'application/pdf',
              size: 2048,
              created_at: '2026-11-01T00:00:00Z',
            },
          ],
        }
      : { data: [] },
  )
  mocks.POST.mockResolvedValueOnce({ error: { code: 'cv_unparseable', detail: 'x' } })
  act(() => setLang('fr'))
  try {
    const user = userEvent.setup()
    renderPage('/cv-review')
    await user.click(await screen.findByRole('button', { name: 'Analyser mon CV' }))
    expect(await screen.findByText(/Impossible de lire du texte/)).toBeInTheDocument()
  } finally {
    act(() => setLang('en'))
  }
})

test('a PDF upload shows the original file with each block marked where it is printed', async () => {
  const user = userEvent.setup()
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/cv-reviews/{review_id}'
      ? { data: review }
      : url.endsWith('/layout')
        ? {
            data: {
              ratios: [1.4],
              boxes: { b2: [{ p: 0, x: 0.1, y: 0.2, w: 0.5, h: 0.03, s: 0, e: 17 }] }, // b1 not found
            },
          }
        : url.endsWith('/pages/{page}')
          ? { data: new Blob(['png'], { type: 'image/png' }) }
          : { data: [] },
  )
  const { container } = renderPage()
  await screen.findByText(/could not be matched/)
  const mark = container.querySelector('[data-cvr-block="b2"]')! // an overlay, not a textarea
  expect(mark).toHaveAttribute('title', 'CV text, line 2')
  expect(mark).toHaveStyle({ left: '10%', top: '20%', width: '50%' })
  expect(screen.queryByLabelText('CV text, line 1')).not.toBeInTheDocument() // not matched in the file
  expect(screen.getByText(/could not be matched/)).toBeInTheDocument()

  await user.click(mark as HTMLElement)
  expect(screen.getByText(/Describes a duty/).closest('article')).toHaveClass('ring-2')
  await user.click(screen.getByRole('button', { name: 'Edit text' }))
  expect(screen.getByLabelText('CV text, line 1').tagName).toBe('TEXTAREA') // every line is back, editable
})
