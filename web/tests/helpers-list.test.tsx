import '@/features/helpers/lib'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HelpersPage } from '@/features/helpers/HelpersPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

test('New helper asks for the type first and creates a built-in helper from the choice', async () => {
  mocks.GET.mockResolvedValue({ data: [], error: undefined })
  mocks.POST.mockResolvedValue({ data: { id: 'x1' }, error: undefined })
  const user = userEvent.setup()
  renderWithApp(<HelpersPage />, { at: '/helpers', path: '/helpers' })

  expect(await screen.findByText('No helper yet')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /^Use:/ })).toHaveLength(5) // templates stay
  await user.click(screen.getByRole('button', { name: 'New helper' }))
  for (const n of ['Cover letter', 'Interview prep', 'CV advice', 'Write my own'])
    expect(screen.getByRole('button', { name: new RegExp(n) })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Interview prep/ }))
  await waitFor(() => expect(mocks.POST).toHaveBeenCalled())
  expect(mocks.POST.mock.calls[0]?.[1].body).toMatchObject({
    name: 'Interview prep',
    spec: { role: 'interview', instructions: '' },
  })
})
