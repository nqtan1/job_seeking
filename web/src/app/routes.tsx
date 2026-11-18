import { type RouteObject } from 'react-router'
import { ErrorScreen } from '@/components/ErrorScreen'
import { tNow } from '@/i18n'
import { AppLayout } from './AppLayout'
import { RequireAuth } from './RequireAuth'

// Pages load on demand: only the layout and auth guard are in the first bundle (sign-in pulls zod
// and react-hook-form, so it is lazy too).
const pages: RouteObject[] = [
  {
    path: '/signin',
    lazy: () => import('./SignInRoute').then((m) => ({ Component: m.SignInRoute })),
  },
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
    HydrateFallback: () => <p className="p-8 text-muted-foreground">{tNow('app.loading')}</p>, // while the first page chunk loads
    children: [
      {
        element: <AppLayout />,
        children: [
          {
            index: true,
            lazy: () =>
              import('@/features/today/TodayPage').then((m) => ({ Component: m.TodayPage })),
          },
          {
            path: '/chat',
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
            path: '/helpers',
            lazy: () =>
              import('@/features/helpers/HelpersPage').then((m) => ({ Component: m.HelpersPage })),
          },
          {
            path: '/tools',
            lazy: () =>
              import('@/features/tools/ToolsPage').then((m) => ({ Component: m.ToolsPage })),
          },
          {
            path: '/tools/:id',
            lazy: () =>
              import('@/features/tools/ToolPage').then((m) => ({ Component: m.ToolPage })),
          },
          {
            path: '/activity',
            lazy: () => import('./ActivityPage').then((m) => ({ Component: m.ActivityPage })),
          },
          {
            path: '/automations',
            lazy: () =>
              import('@/features/helpers/AutomationsPage').then((m) => ({
                Component: m.AutomationsPage,
              })),
          },
          {
            path: '/automations/:flowId',
            lazy: () =>
              import('@/features/helpers/FlowEditor').then((m) => ({ Component: m.FlowEditor })),
          },
          {
            path: '/automations/runs/:runId',
            lazy: () =>
              import('@/features/helpers/RunPage').then((m) => ({ Component: m.RunPage })),
          },
          {
            path: '/helpers/:agentId',
            lazy: () =>
              import('@/features/helpers/HelperEditor').then((m) => ({
                Component: m.HelperEditor,
              })),
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
            path: '/cv-review/:reviewId?',
            lazy: () =>
              import('@/features/cv-review/CvReviewPage').then((m) => ({
                Component: m.CvReviewPage,
              })),
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

// One error screen for every page (a render or chunk-load error would otherwise blank the app).
export const routes: RouteObject[] = [{ errorElement: <ErrorScreen />, children: pages }]
