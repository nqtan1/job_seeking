import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { routes } from '@/app/routes'

// 30 s of freshness: moving between tabs shows cached data at once instead of refetching (each
// refetch costs a token check and a DB read). Mutations still invalidate what they change.
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } })
const router = createBrowserRouter(routes)

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
