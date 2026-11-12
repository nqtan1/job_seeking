import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { RadarBadge } from '@/features/radar/RadarBadge'
import { useRadarStatus, useResults } from '@/features/radar/api'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

test('the menu shows how many new matches are waiting, and nothing when there are none', async () => {
  mocks.GET.mockResolvedValue({ data: { new_matches: 3, running: false } })
  const { unmount } = renderWithApp(<RadarBadge />)
  expect(await screen.findByLabelText('3 new matches')).toHaveTextContent('3')
  unmount()

  mocks.GET.mockResolvedValue({ data: { new_matches: 0, running: false } })
  const again = renderWithApp(<RadarBadge />)
  await new Promise((r) => setTimeout(r, 50))
  expect(again.queryByLabelText(/new matches/)).toBeNull()
})

test('a run that finishes while the page is open reloads the matches', async () => {
  const run = (id: string) => ({ id, finished_at: '2026-11-12T07:30:00Z' })
  const answer = (status: object, results: object[]) =>
    mocks.GET.mockImplementation(async (url: string) => ({
      data: url.endsWith('/status') ? status : results,
    }))
  answer({ new_matches: 0, running: false, last_run: run('a') }, [])
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const Probe = () => {
    const status = useRadarStatus()
    const results = useResults('new')
    return (
      <p>
        {status.data && `matches ${status.data.new_matches}`} {results.data?.map((r) => r.title)}
      </p>
    )
  }
  render(
    <QueryClientProvider client={client}>
      <Probe />
    </QueryClientProvider>,
  )
  await screen.findByText(/matches 0/)
  answer({ new_matches: 1, running: false, last_run: run('b') }, [{ id: 'r', title: 'Stage IA' }])
  await client.invalidateQueries({ queryKey: ['radar-status'] }) // what the 60 s poll does
  expect(await screen.findByText(/Stage IA/)).toBeInTheDocument()
})
