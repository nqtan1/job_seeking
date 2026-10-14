import { act, render, screen } from '@testing-library/react'
import { StepProgress } from '@/components/StepProgress'
import { Button } from '@/components/ui/button'

test('a loading button is disabled and busy; steps advance with time and show elapsed seconds', () => {
  vi.useFakeTimers()
  try {
    render(<Button loading>Generate</Button>)
    const button = screen.getByRole('button', { name: 'Generate' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')

    render(<StepProgress steps={['Reading…', 'Writing…']} every={2000} />)
    expect(screen.getByRole('status')).toHaveTextContent('0 s')
    expect(screen.getAllByText('Reading…')).toHaveLength(2) // sr-only + visible list
    act(() => void vi.advanceTimersByTime(2000))
    expect(screen.getByRole('status')).toHaveTextContent('2 s')
    expect(screen.getAllByText('Writing…')).toHaveLength(2)
  } finally {
    vi.useRealTimers()
  }
})
