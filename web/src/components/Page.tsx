import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { cn } from 'cn'

type Props = {
  title: string
  description?: string
  /** A "back to list" link shown above the title. */
  back?: { to: string; label: string }
  actions?: ReactNode
  /** Full width (split panes); default is a readable 64rem column. */
  wide?: boolean
  children: ReactNode
}

/** Every tool screen: a slim sticky header, then the content filling the main area. */
export function Page({ title, description, back, actions, wide, children }: Props) {
  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-10 flex min-h-14 flex-wrap items-center gap-3 border-b bg-background/85 px-6 py-2 backdrop-blur">
        <div className="min-w-0 flex-1">
          {back && (
            <Link
              to={back.to}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="size-3" />
              {back.label}
            </Link>
          )}
          <h1 className="truncate text-lg font-semibold tracking-tight">{title}</h1>
          {description && <p className="truncate text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions}
      </header>
      <div
        className={cn(
          'mx-auto w-full flex-1 animate-in space-y-6 p-6 duration-200 fade-in',
          wide ? 'max-w-none' : 'max-w-5xl',
        )}
      >
        {children}
      </div>
    </div>
  )
}
