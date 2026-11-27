import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { routes } from '@/app/routes'

const state = vi.hoisted(() => ({ user: undefined as unknown, me: { is_admin: false } as object }))
vi.mock('@/lib/auth', () => ({ useAuthUser: () => state.user, signOut: vi.fn() }))
vi.mock('@/features/auth/SessionGuard', () => ({ SessionGuard: () => null }))
vi.mock('@/features/coach/ChatPage', () => ({ ChatPage: () => <h1>Coach</h1> }))
vi.mock('@/features/today/TodayPage', () => ({ TodayPage: () => <h1>Next step</h1> }))
const recent = vi.hoisted(() => ({ chats: [] as unknown[], letters: [] as unknown[] }))
vi.mock('@/features/coach/api', () => ({ useChats: () => ({ data: recent.chats }) }))
vi.mock('@/features/letters/api', () => ({ useLetters: () => ({ data: recent.letters }) }))
vi.mock('@/features/job-search/api', () => ({
  useJobs: () => ({ data: [{ id: 'j1', data: { company: { name: 'Café Acme' } } }] }),
}))
vi.mock('@/features/auth/SignIn', () => ({ SignIn: () => <h1>Sign in page</h1> }))
vi.mock('@/features/candidate/ProfilePage', () => ({ ProfilePage: () => <h1>Profile</h1> }))
vi.mock('@/features/job-search/JobsPage', () => ({ JobsPage: () => <h1>Jobs</h1> }))
vi.mock('@/features/radar/api', () => ({ useRadarStatus: () => ({ data: { new_matches: 0 } }) }))
vi.mock('@/features/settings/api', () => ({
  useMe: () => ({ data: state.me }),
  useSetLanguage: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/features/admin/AdminUsersPage', () => ({ AdminUsersPage: () => <h1>Users</h1> }))
vi.mock('@/features/settings/SettingsPage', () => ({ SettingsPage: () => <h1>Settings</h1> }))
vi.mock('@/features/tracker/TrackerPage', () => ({ TrackerPage: () => <h1>Tracker</h1> }))
vi.mock('@/features/letters/LettersPage', () => ({ LettersPage: () => <h1>Letters</h1> }))
vi.mock('@/features/letters/LetterPage', () => ({ LetterPage: () => <h1>Letter</h1> }))
vi.mock('@/features/fit/FitPage', () => ({ FitPage: () => <h1>Fit</h1> }))
vi.mock('@/features/tools/ToolsPage', () => ({ ToolsPage: () => <h1>Tools</h1> }))
vi.mock('@/features/helpers/AutomationsPage', () => ({ AutomationsPage: () => <h1>Flows</h1> }))

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

test('signed in: index is Home, the menu switches places, career pages sit in Job search with their tabs, /signin bounces home', async () => {
  state.user = { email: 'a@b.co' }
  const { unmount } = open('/')
  expect(await screen.findByRole('heading', { name: 'Next step' })).toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Section' })).not.toBeInTheDocument()
  const main = within(screen.getByRole('navigation', { name: 'Main' }))
  expect(main.getAllByRole('link').map((a) => a.textContent)).toEqual(['Home', 'Job search']) // helpers off
  main.getByRole('link', { name: 'Job search' }).click()
  expect(await screen.findByRole('heading', { name: 'Tools' })).toBeInTheDocument()
  unmount()

  open('/profile')
  expect(await screen.findByRole('heading', { name: 'Profile' })).toBeInTheDocument()
  const tabs = within(screen.getByRole('navigation', { name: 'Section' }))
  expect(tabs.queryByRole('link', { name: 'Review' })).not.toBeInTheDocument() // flag off in this account
  tabs.getByRole('link', { name: 'Letters' }).click()
  expect(await screen.findByRole('heading', { name: 'Letters' })).toBeInTheDocument()
  const nav = within(screen.getByRole('navigation', { name: 'Main' }))
  expect(nav.getByRole('link', { name: 'Job search' })).toHaveAttribute('aria-current', 'page')
  unmount()

  open('/signin')
  expect(await screen.findByRole('heading', { name: 'Next step' })).toBeInTheDocument()
})

test('with helpers on: Activity and Studio join the menu, the coach chat sits in Home, Studio holds Agents, Flows and Tools', async () => {
  state.user = { email: 'a@b.co' }
  state.me = { is_admin: false, helpers_enabled: true }
  const { unmount } = open('/chat')
  expect(await screen.findByRole('heading', { name: 'Coach' })).toBeInTheDocument()
  const main = within(screen.getByRole('navigation', { name: 'Main' }))
  expect(main.getAllByRole('link').map((a) => a.textContent)).toEqual([
    'Home',
    'Job search',
    'Activity',
    'Studio',
  ])
  expect(main.getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page')
  unmount()

  open('/automations')
  const tabs = within(await screen.findByRole('navigation', { name: 'Section' }))
  expect(tabs.getAllByRole('link').map((a) => a.textContent)).toEqual(['Agents', 'Flows', 'Tools'])
  expect(
    within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Studio' }),
  ).toHaveAttribute('aria-current', 'page')
  state.me = { is_admin: false }
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
