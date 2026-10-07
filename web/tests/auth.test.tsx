import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { SignIn } from '@/features/auth/SignIn'
import { getAuthHeaders, signUpWithEmail } from '@/lib/auth'

const fb = vi.hoisted(() => ({
  currentUser: { getIdToken: vi.fn().mockResolvedValue('tok') } as {
    getIdToken: () => Promise<string>
  } | null,
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
  GoogleAuthProvider: class {},
  createUserWithEmailAndPassword: fb.createUser,
  sendEmailVerification: fb.sendVerification,
  signInWithEmailAndPassword: fb.signIn,
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
  onAuthStateChanged: vi.fn(),
}))

beforeEach(() => vi.clearAllMocks())

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
