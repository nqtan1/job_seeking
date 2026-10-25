import { act, render, screen } from '@testing-library/react'
import { ColdStartNotice } from '@/app/ColdStartNotice'

const state = vi.hoisted(() => ({ pending: true }))
vi.mock('@/features/settings/api', () => ({ useMe: () => ({ isPending: state.pending }) }))

test('the wake-up notice appears only when the first call is slow, and goes when it answers', () => {
  vi.useFakeTimers()
  state.pending = true
  const { rerender } = render(<ColdStartNotice />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  act(() => void vi.advanceTimersByTime(3100))
  expect(screen.getByRole('status')).toHaveTextContent('Waking up the server')
  state.pending = false
  rerender(<ColdStartNotice />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  vi.useRealTimers()
})
