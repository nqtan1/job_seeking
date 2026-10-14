import { act, render, screen } from '@testing-library/react'
import { idleState, registerEndSession, useIdleSession } from '@/lib/session'

const MIN = 60_000

test('idle boundaries: active, warning in the last 2 minutes, expired at the limit', () => {
  const limit = 30 * MIN
  expect(idleState(28 * MIN - 1, 0, limit)).toBe('active')
  expect(idleState(28 * MIN, 0, limit)).toBe('warning')
  expect(idleState(30 * MIN - 1, 0, limit)).toBe('warning')
  expect(idleState(30 * MIN, 0, limit)).toBe('expired')
})

function Probe({ limit }: { limit: number }) {
  const s = useIdleSession(limit, true)
  return (
    <>
      <p>state:{s.state}</p>
      <button onClick={s.touch}>stay</button>
    </>
  )
}

test('the hook warns at limit-2min, "stay" resets it, and expiry ends the session', async () => {
  vi.useFakeTimers()
  const end = vi.fn()
  registerEndSession(end)
  try {
    render(<Probe limit={30} />)
    await act(async () => void vi.advanceTimersByTime(27 * MIN))
    expect(screen.getByText('state:active')).toBeInTheDocument()
    await act(async () => void vi.advanceTimersByTime(1 * MIN + 2_000))
    expect(screen.getByText('state:warning')).toBeInTheDocument()

    await act(async () => void screen.getByText('stay').click())
    expect(screen.getByText('state:active')).toBeInTheDocument()
    expect(end).not.toHaveBeenCalled()

    await act(async () => void vi.advanceTimersByTime(30 * MIN + 2_000))
    expect(end).toHaveBeenCalledWith('idle')
  } finally {
    registerEndSession(undefined)
    vi.useRealTimers()
  }
})
