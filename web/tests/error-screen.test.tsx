import { render, screen, waitFor } from '@testing-library/react'
import type { ErrorEvent } from '@sentry/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { ErrorScreen } from '@/components/ErrorScreen'
import { scrub } from '@/lib/sentry'

const sentry = vi.hoisted(() => ({ captureException: vi.fn() }))
vi.mock('@sentry/react', () => sentry)

const crash = (thrown: unknown) => {
  const Boom = () => {
    throw thrown
  }
  vi.spyOn(console, 'error').mockImplementation(() => {})
  render(
    <RouterProvider
      router={createMemoryRouter([
        { errorElement: <ErrorScreen />, children: [{ path: '/', element: <Boom /> }] },
      ])}
    />,
  )
}

test('a render error shows the error screen and is reported', async () => {
  crash(new Error('boom'))
  expect(await screen.findByText('Something went wrong')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
  await waitFor(() => expect(sentry.captureException).toHaveBeenCalled())
})

test('an API error shows its request id and tags the report', async () => {
  crash({ code: 'conflict', detail: 'x', request_id: 'abc123' })
  expect(await screen.findByText('request id: abc123')).toBeInTheDocument()
  await waitFor(() =>
    expect(sentry.captureException).toHaveBeenLastCalledWith(expect.anything(), {
      tags: { request_id: 'abc123' },
    }),
  )
})

test('beforeSend keeps type and stack, drops anything personal', () => {
  const event = {
    message: 'hi jane@example.com',
    user: { email: 'jane@example.com' },
    request: { url: 'https://app/x?email=jane@example.com', headers: { Cookie: 's' } },
    extra: { cv: 'text' },
    exception: {
      values: [
        {
          type: 'TypeError',
          value: 'jane@example.com',
          stacktrace: { frames: [{ function: 'f' }] },
        },
      ],
    },
    breadcrumbs: [
      { category: 'fetch', message: 'jane', data: { url: '/api/x?q=jane', method: 'GET' } },
      { category: 'navigation', data: { from: '/a?t=1', to: '/b#k' } },
    ],
  } as unknown as ErrorEvent
  const out = JSON.stringify(scrub(event))
  expect(out).not.toMatch(/jane|Cookie|cv|\?|#/)
  expect(out).toContain('TypeError')
  expect(out).toContain('"function":"f"')
  expect(out).toContain('/api/x')
})
