import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { routes } from '@/app/routes'

const state = vi.hoisted(() => ({ user: undefined as unknown }))
vi.mock('@/lib/auth', () => ({ useAuthUser: () => state.user, signOut: vi.fn() }))
vi.mock('@/features/coach/ChatPage', () => ({ ChatPage: () => <h1>Coach</h1> }))
vi.mock('@/features/coach/api', () => ({ useConversations: () => ({ data: [] }) }))
vi.mock('@/features/letters/api', () => ({ useLetters: () => ({ data: [] }) }))
vi.mock('@/features/auth/SignIn', () => ({ SignIn: () => <h1>Sign in page</h1> }))
vi.mock('@/features/candidate/ProfilePage', () => ({ ProfilePage: () => <h1>Profile</h1> }))
vi.mock('@/features/job-search/JobsPage', () => ({ JobsPage: () => <h1>Jobs</h1> }))
vi.mock('@/features/radar/api', () => ({ useRadarStatus: () => ({ data: { new_matches: 0 } }) }))
vi.mock('@/features/settings/api', () => ({ useMe: () => ({ data: { is_admin: false } }) }))
vi.mock('@/features/admin/AdminUsersPage', () => ({ AdminUsersPage: () => <h1>Users</h1> }))
vi.mock('@/features/settings/SettingsPage', () => ({ SettingsPage: () => <h1>Settings</h1> }))
vi.mock('@/features/tracker/TrackerPage', () => ({ TrackerPage: () => <h1>Tracker</h1> }))
vi.mock('@/features/letters/LettersPage', () => ({ LettersPage: () => <h1>Letters</h1> }))
vi.mock('@/features/letters/LetterPage', () => ({ LetterPage: () => <h1>Letter</h1> }))
vi.mock('@/features/fit/FitPage', () => ({ FitPage: () => <h1>Fit</h1> }))

const open = (path: string) =>
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)

test('protected routes: loading while unresolved, redirect when signed out', () => {
  state.user = undefined
  const { unmount } = open('/jobs')
  expect(screen.getByText('Loading…')).toBeInTheDocument()
  unmount()

  state.user = null
  open('/jobs')
  expect(screen.getByText('Sign in page')).toBeInTheDocument()
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
  expect(localStorage.getItem('theme')).toBe('dark') // the choice persists
  await userEvent.click(screen.getByRole('menuitem', { name: 'Settings' }))
  expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
})

test('after sign-in the user returns to the page they asked for', async () => {
  state.user = null
  const router = createMemoryRouter(routes, { initialEntries: ['/tracker'] })
  render(<RouterProvider router={router} />)
  expect(screen.getByText('Sign in page')).toBeInTheDocument()
  state.user = { email: 'a@b.co' }
  await router.navigate('/signin', { state: { from: { pathname: '/tracker' } } })
  expect(await screen.findByRole('heading', { name: 'Tracker' })).toBeInTheDocument()
})
