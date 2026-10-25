import { type RouteObject } from 'react-router'
import { AppLayout } from './AppLayout'
import { RequireAuth } from './RequireAuth'
import { SignInRoute } from './SignInRoute'

// Pages load on demand: only the sign-in, layout and auth guard are in the first bundle.
export const routes: RouteObject[] = [
  { path: '/signin', element: <SignInRoute /> },
  {
    path: '/privacy',
    lazy: () =>
      import('@/features/privacy/PrivacyPage').then((m) => ({ Component: m.PrivacyPage })),
  },
  {
    path: '/radar/link',
    lazy: () => import('@/features/radar/LinkPage').then((m) => ({ Component: m.LinkPage })),
  },
  {
    element: <RequireAuth />,
    HydrateFallback: () => <p className="p-8 text-muted-foreground">Loading…</p>, // while the first page chunk loads
    children: [
      {
        element: <AppLayout />,
        children: [
          {
            index: true,
            lazy: () =>
              import('@/features/coach/ChatPage').then((m) => ({ Component: m.ChatPage })),
          },
          {
            path: '/chat/:conversationId',
            lazy: () =>
              import('@/features/coach/ChatPage').then((m) => ({ Component: m.ChatPage })),
          },
          {
            path: '/profile',
            lazy: () =>
              import('@/features/candidate/ProfilePage').then((m) => ({
                Component: m.ProfilePage,
              })),
          },
          {
            path: '/jobs',
            lazy: () =>
              import('@/features/job-search/JobsPage').then((m) => ({ Component: m.JobsPage })),
          },
          {
            path: '/radar',
            lazy: () =>
              import('@/features/radar/RadarPage').then((m) => ({ Component: m.RadarPage })),
          },
          {
            path: '/tracker',
            lazy: () =>
              import('@/features/tracker/TrackerPage').then((m) => ({ Component: m.TrackerPage })),
          },
          {
            path: '/tracker/proof',
            lazy: () =>
              import('@/features/tracker/ProofPage').then((m) => ({ Component: m.ProofPage })),
          },
          {
            path: '/tracker/:applicationId/prep',
            lazy: () =>
              import('@/features/tracker/PrepPage').then((m) => ({ Component: m.PrepPage })),
          },
          {
            path: '/settings',
            lazy: () =>
              import('@/features/settings/SettingsPage').then((m) => ({
                Component: m.SettingsPage,
              })),
          },
          {
            path: '/admin',
            lazy: () =>
              import('@/features/admin/AdminUsersPage').then((m) => ({
                Component: m.AdminUsersPage,
              })),
          },
          {
            path: '/admin/ai',
            lazy: () =>
              import('@/features/admin/AdminAiPage').then((m) => ({ Component: m.AdminAiPage })),
          },
          {
            path: '/letters',
            lazy: () =>
              import('@/features/letters/LettersPage').then((m) => ({ Component: m.LettersPage })),
          },
          {
            path: '/letters/:letterId',
            lazy: () =>
              import('@/features/letters/LetterPage').then((m) => ({ Component: m.LetterPage })),
          },
          {
            path: '/jobs/:jobId/fit',
            lazy: () => import('@/features/fit/FitPage').then((m) => ({ Component: m.FitPage })),
          },
        ],
      },
    ],
  },
]
