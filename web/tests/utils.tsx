import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { Toaster } from '@/components/Toaster'

/** Render a page with a fresh, retry-less QueryClient; `route` mounts it at a router path. */
export function renderWithApp(ui: ReactElement, route?: { at: string; path: string }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const page = route ? (
    <MemoryRouter initialEntries={[route.at]}>
      <Routes>
        <Route path={route.path} element={ui} />
      </Routes>
    </MemoryRouter>
  ) : (
    ui
  )
  return render(
    <QueryClientProvider client={client}>
      {page}
      <Toaster />
    </QueryClientProvider>,
  )
}
