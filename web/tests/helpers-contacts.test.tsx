import '@/features/helpers/lib'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ContactsTab } from '@/features/helpers/Recipients'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), DELETE: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

it('shows a pending contact, and adds a new one', async () => {
  mocks.GET.mockResolvedValue({
    data: [
      { id: 'r1', email: 'bob@example.com', status: 'pending', created_at: '2026-11-01T00:00:00Z' },
    ],
  })
  mocks.POST.mockResolvedValue({ data: { id: 'r2' } })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ContactsTab />
    </QueryClientProvider>,
  )
  expect(await screen.findByText('Waiting for their OK')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Remove bob@example.com' })).toBeInTheDocument()

  await userEvent.type(screen.getByLabelText('Add a contact'), '  amy@example.com ')
  await userEvent.click(screen.getByRole('button', { name: 'Add' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/email-recipients', {
      body: { email: 'amy@example.com' },
    }),
  )
  expect(await screen.findByText(/We sent amy@example.com a confirmation link/)).toBeInTheDocument()
})
