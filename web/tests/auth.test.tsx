import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { SignIn } from '@/features/auth/SignIn'
import { SignInMethods } from '@/features/auth/SignInMethods'
import { addPassword, getAuthHeaders, signUpWithEmail } from '@/lib/auth'

const fb = vi.hoisted(() => ({
  currentUser: { getIdToken: vi.fn().mockResolvedValue('tok') } as Record<string, unknown> | null,
  link: vi.fn(),
  reauthPopup: vi.fn(),
  reset: vi.fn(),
  createUser: vi.fn(),
  sendVerification: vi.fn(),
  signIn: vi.fn(),
}))

vi.mock('@/lib/firebase', () => ({
  auth: {
    get currentUser() {
      return fb.currentUser
    },
  },
}))
vi.mock('firebase/auth', () => ({
  GoogleAuthProvider: class {
    setCustomParameters() {}
  },
  EmailAuthProvider: { credential: (email: string, password: string) => ({ email, password }) },
  linkWithCredential: fb.link,
  linkWithPopup: vi.fn(),
  sendPasswordResetEmail: fb.reset,
  setPersistence: vi.fn().mockResolvedValue(undefined),
  browserLocalPersistence: {},
  browserSessionPersistence: {},
  reauthenticateWithCredential: vi.fn(),
  reauthenticateWithPopup: fb.reauthPopup,
  createUserWithEmailAndPassword: fb.createUser,
  sendEmailVerification: fb.sendVerification,
  signInWithEmailAndPassword: fb.signIn,
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
  onAuthStateChanged: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
  fb.currentUser = { getIdToken: vi.fn().mockResolvedValue('tok') }
})

test('auth header carries the current ID token, empty when signed out', async () => {
  expect(await getAuthHeaders()).toEqual({ Authorization: 'Bearer tok' })
  fb.currentUser = null
  expect(await getAuthHeaders()).toEqual({})
})

test('sign-up sends the verification email', async () => {
  fb.createUser.mockResolvedValue({ user: { uid: 'u' } })
  await signUpWithEmail('a@b.co', 'password1')
  expect(fb.sendVerification).toHaveBeenCalledWith({ uid: 'u' })
})

test('sign-in form validates input, then maps SDK errors to a safe message', async () => {
  const user = userEvent.setup()
  render(
    <MemoryRouter>
      <SignIn />
    </MemoryRouter>,
  )
  await user.type(screen.getByLabelText('Email'), 'nope')
  await user.type(screen.getByLabelText('Password'), 'short')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
  expect(fb.signIn).not.toHaveBeenCalled()

  await user.clear(screen.getByLabelText('Email'))
  await user.type(screen.getByLabelText('Email'), 'a@b.co')
  await user.clear(screen.getByLabelText('Password'))
  await user.type(screen.getByLabelText('Password'), 'password1')
  fb.signIn.mockRejectedValue({ code: 'auth/invalid-credential', message: 'raw sdk text' })
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  await waitFor(() => expect(screen.getByText('Wrong email or password.')).toBeInTheDocument())
  expect(screen.queryByText(/raw sdk text/)).not.toBeInTheDocument()
})

test('a sign-up whose verification mail fails still succeeds; passwords must match', async () => {
  fb.createUser.mockResolvedValue({ user: { uid: 'u' } })
  fb.sendVerification.mockRejectedValue(new Error('mail down'))
  await expect(signUpWithEmail('a@b.co', 'password1')).resolves.toBeDefined()

  const user = userEvent.setup()
  render(
    <MemoryRouter>
      <SignIn />
    </MemoryRouter>,
  )
  await user.click(screen.getByRole('button', { name: 'No account? Sign up' }))
  await user.type(screen.getByLabelText('Email'), '  Ada@B.co ')
  await user.type(screen.getByLabelText('Password'), 'password1')
  await user.type(screen.getByLabelText('Confirm password'), 'password2')
  await user.click(screen.getByRole('button', { name: 'Sign up' }))
  expect(await screen.findByText('The two passwords are not the same.')).toBeInTheDocument()
  expect(fb.createUser).toHaveBeenCalledTimes(1) // only the direct call above

  await user.clear(screen.getByLabelText('Confirm password'))
  await user.type(screen.getByLabelText('Confirm password'), 'password1')
  await user.click(screen.getByRole('button', { name: 'Sign up' }))
  await waitFor(() => expect(fb.createUser).toHaveBeenCalledTimes(2))
  expect(fb.createUser.mock.calls[1].slice(1)).toEqual(['ada@b.co', 'password1']) // trimmed, lower-case
})

test('an older short password can still sign in; a reset gives the same answer for any address', async () => {
  const user = userEvent.setup()
  render(
    <MemoryRouter>
      <SignIn />
    </MemoryRouter>,
  )
  await user.type(screen.getByLabelText('Email'), 'a@b.co')
  await user.type(screen.getByLabelText('Password'), 'abc123')
  fb.signIn.mockRejectedValue({ code: 'auth/invalid-credential' })
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText(/Signed up with Google/)).toBeInTheDocument() // the way in is named

  await user.click(screen.getByRole('button', { name: 'Forgot your password?' }))
  fb.reset.mockRejectedValue({ code: 'auth/user-not-found' }) // the emulator; production is silent
  await user.click(screen.getByRole('button', { name: 'Send the reset link' }))
  expect(await screen.findByText(/we sent a reset link/)).toBeInTheDocument()
  expect(fb.reset).toHaveBeenCalledWith(expect.anything(), 'a@b.co')
})

test('a Google account gets a password: a stale sign-in is renewed once, then it links', async () => {
  fb.currentUser = {
    getIdToken: vi.fn(),
    reload: vi.fn(),
    email: 'g@b.co',
    emailVerified: true,
    providerData: [{ providerId: 'google.com' }],
  }
  fb.link
    .mockRejectedValueOnce({ code: 'auth/requires-recent-login' })
    .mockResolvedValueOnce(undefined)
  await addPassword('password1')
  expect(fb.reauthPopup).toHaveBeenCalledTimes(1)
  expect(fb.link).toHaveBeenCalledTimes(2)

  const user = userEvent.setup()
  render(<SignInMethods />)
  await user.type(screen.getByLabelText('New password'), 'password1')
  await user.type(screen.getByLabelText('Confirm password'), 'different1')
  await user.click(screen.getByRole('button', { name: 'Add a password' }))
  expect(await screen.findByText('The two passwords are not the same.')).toBeInTheDocument()
})
