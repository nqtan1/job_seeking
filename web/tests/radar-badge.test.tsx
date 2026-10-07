import { screen } from '@testing-library/react'
import { RadarBadge } from '@/features/radar/RadarBadge'
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
