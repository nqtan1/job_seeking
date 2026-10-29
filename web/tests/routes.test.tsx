import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { routes } from '@/app/routes'

const state = vi.hoisted(() => ({ user: undefined as unknown }))
vi.mock('@/lib/auth', () => ({ useAuthUser: () => state.user, signOut: vi.fn() }))
vi.mock('@/features/auth/SessionGuard', () => ({ SessionGuard: () => null }))
vi.mock('@/features/coach/ChatPage', () => ({ ChatPage: () => <h1>Coach</h1> }))
const recent = vi.hoisted(() => ({ chats: [] as unknown[], letters: [] as unknown[] }))
vi.mock('@/features/coach/api', () => ({ useConversations: () => ({ data: recent.chats }) }))
vi.mock('@/features/letters/api', () => ({ useLetters: () => ({ data: recent.letters }) }))
vi.mock('@/features/job-search/api', () => ({
  useJobs: () => ({ data: [{ id: 'j1', data: { company: { name: 'Café Acme' } } }] }),
}))
vi.mock('@/features/auth/SignIn', () => ({ SignIn: () => <h1>Sign in page</h1> }))
vi.mock('@/features/candidate/ProfilePage', () => ({ ProfilePage: () => <h1>Profile</h1> }))
vi.mock('@/features/job-search/JobsPage', () => ({ JobsPage: () => <h1>Jobs</h1> }))
vi.mock('@/features/radar/api', () => ({ useRadarStatus: () => ({ data: { new_matches: 0 } }) }))
vi.mock('@/features/settings/api', () => ({
  useMe: () => ({ data: { is_admin: false } }),
  useSetLanguage: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/features/admin/AdminUsersPage', () => ({ AdminUsersPage: () => <h1>Users</h1> }))
vi.mock('@/features/settings/SettingsPage', () => ({ SettingsPage: () => <h1>Settings</h1> }))
vi.mock('@/features/tracker/TrackerPage', () => ({ TrackerPage: () => <h1>Tracker</h1> }))
vi.mock('@/features/letters/LettersPage', () => ({ LettersPage: () => <h1>Letters</h1> }))
vi.mock('@/features/letters/LetterPage', () => ({ LetterPage: () => <h1>Letter</h1> }))
vi.mock('@/features/fit/FitPage', () => ({ FitPage: () => <h1>Fit</h1> }))

const open = (path: string) =>
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)

test('protected routes: loading while unresolved, redirect when signed out', async () => {
  state.user = undefined
  const { unmount } = open('/jobs')
  await waitFor(() => expect(screen.getByText('Loading…')).toBeInTheDocument())
  unmount()

  state.user = null
  open('/jobs')
  expect(await screen.findByText('Sign in page')).toBeInTheDocument()
})

test('signed in: index is the coach, nav links switch routes, /signin bounces home', async () => {
  state.user = { email: 'a@b.co' }
  const { unmount } = open('/')
  expect(await screen.findByRole('heading', { name: 'Coach' })).toBeInTheDocument()
  screen.getByRole('link', { name: 'Tracker' }).click()
  expect(await screen.findByRole('heading', { name: 'Tracker' })).toBeInTheDocument()
  unmount()

  open('/signin')
  expect(await screen.findByRole('heading', { name: 'Coach' })).toBeInTheDocument()
})

test('account menu: shows the email, opens settings, signs out', async () => {
  state.user = { email: 'a@b.co' }
  open('/')
  await userEvent.click(await screen.findByRole('button', { name: 'Account menu' }))
  expect(screen.getByText('a@b.co', { selector: 'p' })).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Dark' }))
  expect(document.documentElement).toHaveClass('dark')
  expect(localStorage.getItem('theme')).toBe('dark')
  await userEvent.click(screen.getByRole('menuitem', { name: 'Settings' }))
  expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
})

test('after sign-in the user returns to the page they asked for', async () => {
  state.user = null
  const router = createMemoryRouter(routes, { initialEntries: ['/tracker'] })
  render(<RouterProvider router={router} />)
  expect(await screen.findByText('Sign in page')).toBeInTheDocument()
  state.user = { email: 'a@b.co' }
  await router.navigate('/signin', { state: { from: { pathname: '/tracker' } } })
  expect(await screen.findByRole('heading', { name: 'Tracker' })).toBeInTheDocument()
})

test('sidebar recent: grouped by day, merged by time, employer chip when known', async () => {
  state.user = { email: 'a@b.co' }
  const ago = (d: number) => new Date(Date.now() - d * 864e5).toISOString()
  recent.chats = [{ id: 'c1', title: 'Prep', job_id: 'j1', updated_at: ago(0) }]
  recent.letters = [
    { id: 'l1', job_id: null, content: { subject: 'Old letter' }, updated_at: ago(30) },
  ]
  open('/')
  const nav = await screen.findByRole('navigation', { name: 'Recent' })
  const heads = Array.from(nav.querySelectorAll('p')).map((p) => p.textContent)
  expect(heads).toEqual(['Today', 'Earlier'])
  expect(screen.getByRole('link', { name: /Prep/ })).toHaveTextContent('Café Acme')
  expect(screen.getByRole('link', { name: 'Old letter' })).toBeInTheDocument()
  recent.chats = []
  recent.letters = []
})
