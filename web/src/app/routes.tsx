import { type RouteObject } from 'react-router'
import { ChatPage } from '@/features/coach/ChatPage'
import { ProfilePage } from '@/features/candidate/ProfilePage'
import { JobsPage } from '@/features/job-search/JobsPage'
import { FitPage } from '@/features/fit/FitPage'
import { LetterPage } from '@/features/letters/LetterPage'
import { LettersPage } from '@/features/letters/LettersPage'
import { AdminUsersPage } from '@/features/admin/AdminUsersPage'
import { AdminAiPage } from '@/features/admin/AdminAiPage'
import { RadarPage } from '@/features/radar/RadarPage'
import { PrepPage } from '@/features/tracker/PrepPage'
import { TrackerPage } from '@/features/tracker/TrackerPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { PrivacyPage } from '@/features/privacy/PrivacyPage'
import { AppLayout } from './AppLayout'
import { RequireAuth } from './RequireAuth'
import { SignInRoute } from './SignInRoute'

export const routes: RouteObject[] = [
  { path: '/signin', element: <SignInRoute /> },
  { path: '/privacy', element: <PrivacyPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <ChatPage /> },
          { path: '/chat/:conversationId', element: <ChatPage /> },
          { path: '/profile', element: <ProfilePage /> },
          { path: '/jobs', element: <JobsPage /> },
          { path: '/radar', element: <RadarPage /> },
          { path: '/tracker', element: <TrackerPage /> },
          { path: '/tracker/:applicationId/prep', element: <PrepPage /> },
          { path: '/settings', element: <SettingsPage /> },
          { path: '/admin', element: <AdminUsersPage /> },
          { path: '/admin/ai', element: <AdminAiPage /> },
          { path: '/letters', element: <LettersPage /> },
          { path: '/letters/:letterId', element: <LetterPage /> },
          { path: '/jobs/:jobId/fit', element: <FitPage /> },
        ],
      },
    ],
  },
]
