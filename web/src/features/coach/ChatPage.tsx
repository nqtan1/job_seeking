import { useQueryClient } from '@tanstack/react-query'
import { Briefcase, FileText, SendHorizontal, Sparkles, UserRound } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { Checklist } from '@/features/pipeline/Checklist'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Skeleton } from '@/components/Skeleton'
import { Button, buttonVariants } from '@/components/ui/button'
import { useProfile } from '@/features/candidate/api'
import { cn } from 'cn'
import { createConversation, streamMessage, useMessages } from './api'

const MAX = 4000
const PROMPTS = [
  { icon: UserRound, text: 'Review my CV', send: 'Review my CV and tell me what to improve.' },
  {
    icon: Sparkles,
    text: 'Prepare for an interview',
    send: 'Help me prepare for an interview. Ask me the first question.',
  },
  {
    icon: Briefcase,
    text: 'Which job should I apply to first?',
    send: 'Look at the jobs I saved and my profile. Which should I apply to first, and why?',
  },
  {
    icon: FileText,
    text: 'Write a follow-up email',
    send: 'Help me write a short follow-up email for an application I sent a week ago with no reply.',
  },
]
const LINKS = [
  { icon: Briefcase, text: 'Analyse a job', to: '/jobs' },
  { icon: FileText, text: 'Write a cover letter', to: '/letters' },
]
const card =
  'flex items-center gap-2 rounded-xl border bg-card p-3 text-left text-sm shadow-xs transition-colors hover:bg-accent'

function Bubble({ role, children }: { role: 'user' | 'assistant'; children: string }) {
  const user = role === 'user'
  return (
    <div className={cn('flex', user && 'justify-end')}>
      <p
        className={cn(
          'max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap',
          user ? 'bg-primary text-primary-foreground' : 'bg-muted',
        )}
      >
        {children}
      </p>
    </div>
  )
}

/** The home screen: the career coach. `/` starts a chat; `/chat/:conversationId` reopens one. */
export function ChatPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const profile = useProfile()
  const history = useMessages(conversationId)
  const [params] = useSearchParams()
  // `/?ask=…` (from the tracker) prefills the box; the user reviews it and sends.
  const [text, setText] = useState(params.get('ask') ?? '')
  const [pending, setPending] = useState<{ user: string; assistant: string }>()
  const [error, setError] = useState<unknown>()
  const end = useRef<HTMLDivElement>(null)
  const abort = useRef<AbortController>(undefined)

  useEffect(() => () => abort.current?.abort(), [])
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' }) // may return a Promise: never return it
  }, [history.data, pending])

  const send = async (content: string) => {
    if (!content.trim() || pending) return
    setError(undefined)
    setText('')
    setPending({ user: content, assistant: '' })
    abort.current = new AbortController()
    try {
      const id = conversationId ?? (await createConversation()).id
      await streamMessage(
        id,
        content,
        (t) => setPending((p) => p && { ...p, assistant: p.assistant + t }),
        abort.current.signal,
      )
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['messages', id] }),
        qc.invalidateQueries({ queryKey: ['conversations'] }),
      ])
      setPending(undefined)
      if (!conversationId) navigate(`/chat/${id}`, { replace: true })
    } catch (e) {
      if (abort.current.signal.aborted) return
      setPending(undefined)
      setText(content) // nothing was stored; let the user resend
      setError(e)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void send(text)
  }
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send(text)
    }
  }

  if (profile.isPending) return <Skeleton className="m-6 h-24" />
  if (!profile.data && !profile.isError)
    return (
      <div className="mx-auto max-w-lg p-6 pt-24">
        <EmptyState
          icon={UserRound}
          title="Start with your CV"
          description="The coach reads your profile to give advice that fits you. Upload your CV and come back."
          action={
            <Link to="/profile" className={buttonVariants()}>
              Upload your CV
            </Link>
          }
        />
      </div>
    )

  const shown = history.data ?? []
  const empty = shown.length === 0 && !pending && !history.isLoading

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center border-b px-6">
        <h1 className="text-lg font-semibold tracking-tight">Career coach</h1>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-4 p-6">
          {history.isError && <ErrorMessage error={history.error} />}
          {empty && (
            <div className="space-y-6 pt-10 text-center">
              <h2 className="text-2xl font-semibold tracking-tight">What can I help you with?</h2>
              <Checklist />
              <div className="mx-auto grid max-w-xl gap-2 sm:grid-cols-2">
                {PROMPTS.map(({ icon: Icon, text: label, send: msg }) => (
                  <button key={label} className={card} onClick={() => void send(msg)}>
                    <Icon className="size-4 text-primary" />
                    {label}
                  </button>
                ))}
                {LINKS.map(({ icon: Icon, text: label, to }) => (
                  <Link key={label} to={to} className={card}>
                    <Icon className="size-4 text-primary" />
                    {label}
                  </Link>
                ))}
              </div>
            </div>
          )}
          {shown.map((m) => (
            <Bubble key={m.id} role={m.role}>
              {m.content}
            </Bubble>
          ))}
          {pending && <Bubble role="user">{pending.user}</Bubble>}
          {pending &&
            (pending.assistant ? (
              <Bubble role="assistant">{pending.assistant}</Bubble>
            ) : (
              <p role="status" className="text-sm text-muted-foreground">
                Thinking…
              </p>
            ))}
          {error != null && <ErrorMessage error={error} />}
          <div ref={end} />
        </div>
      </div>
      <form onSubmit={submit} className="shrink-0 border-t bg-background p-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border bg-card p-2 shadow-xs focus-within:ring-3 focus-within:ring-ring/40">
          <textarea
            aria-label="Message"
            rows={1}
            value={text}
            maxLength={MAX}
            placeholder="Ask your coach…"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none [field-sizing:content]"
          />
          <Button type="submit" size="icon" aria-label="Send" disabled={!text.trim() || !!pending}>
            <SendHorizontal />
          </Button>
        </div>
      </form>
    </div>
  )
}
