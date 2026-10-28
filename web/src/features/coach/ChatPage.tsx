import { useQueryClient } from '@tanstack/react-query'
import {
  Briefcase,
  Check,
  Copy,
  FileText,
  RefreshCw,
  SendHorizontal,
  Sparkles,
  Square,
  UserRound,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { Checklist } from '@/features/pipeline/Checklist'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Skeleton } from '@/components/Skeleton'
import { Button, buttonVariants } from '@/components/ui/button'
import { useProfile } from '@/features/candidate/api'
import { useT, type Key } from '@/i18n'
import { cn } from 'cn'
import { useJobs } from '@/features/job-search/api'
import {
  createConversation,
  regenerateReply,
  streamMessage,
  useConversation,
  useMessages,
  useSetFocus,
  type Citation,
  type OnEvent,
  type StreamData,
} from './api'
import { Activity, Sources } from './Activity'
import { stepsFromMeta, type Context, type Step } from './activity'
import { DeleteChatButton } from './DeleteChatButton'
import { Markdown } from './Markdown'
import { companyOf } from '@/features/job-search/label'

const MAX = 4000

/** The reply being streamed: everything the events have said so far. */
type Pending = {
  user: string
  assistant: string
  steps: Step[]
  context?: Context
  citations: Citation[]
  suggestions?: string
  notices: string[]
  replacing: boolean // regenerating: the stored last reply is hidden meanwhile
}

function applyEvent(p: Pending, name: string, data: StreamData): Pending {
  switch (name) {
    case 'context':
      return { ...p, context: data as Context }
    case 'step': {
      const step = data as unknown as Step
      const i = p.steps.findIndex((s) => s.id === step.id)
      const steps = i < 0 ? [...p.steps, step] : p.steps.map((s, j) => (j === i ? step : s))
      return { ...p, steps }
    }
    case 'token':
      return { ...p, assistant: p.assistant + String(data.text ?? '') }
    case 'citations':
      return { ...p, citations: (data.items as Citation[]) ?? [] }
    case 'suggestions':
      return { ...p, suggestions: String(data.html ?? '') }
    case 'notice':
      return { ...p, notices: [...p.notices, String(data.code)] }
    default:
      return p
  }
}
const PROMPTS = [
  { icon: UserRound, key: 'cv' },
  { icon: Sparkles, key: 'interview' },
  { icon: Briefcase, key: 'first_job' },
  { icon: FileText, key: 'follow_up' },
] as const
const LINKS = [
  { icon: Briefcase, key: 'jobs', to: '/jobs' },
  { icon: FileText, key: 'letters', to: '/letters' },
] as const
const card =
  'flex items-center gap-2 rounded-xl border bg-card p-3 text-left text-sm shadow-xs transition-colors hover:bg-accent'

function CopyButton({ text }: { text: string }) {
  const t = useT()
  const [done, setDone] = useState(false)
  return (
    <button
      type="button"
      aria-label={t('coach.copy_aria')}
      className="mt-1 inline-flex items-center gap-1 rounded text-xs text-muted-foreground hover:text-foreground"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setDone(true)
          setTimeout(() => setDone(false), 1500)
        })
      }}
    >
      {done ? <Check className="size-3" /> : <Copy className="size-3" />}
      {done ? t('coach.copied') : t('coach.copy')}
    </button>
  )
}

function Bubble({
  role,
  children,
  streaming,
}: {
  role: 'user' | 'assistant'
  children: string
  streaming?: boolean
}) {
  const user = role === 'user'
  return (
    <div className={cn('flex', user && 'justify-end')}>
      <div className={cn('max-w-[85%]', user && 'flex flex-col items-end')}>
        <div
          className={cn(
            'rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
            user ? 'bg-primary text-primary-foreground whitespace-pre-wrap' : 'bg-muted',
          )}
        >
          {user ? children : <Markdown>{children}</Markdown>}
        </div>
        {!user && !streaming && <CopyButton text={children} />}
      </div>
    </div>
  )
}

/** The job the coach is focused on: a chip with a remove action, or a picker to attach one.
 *  ponytail: a native select over the inbox list (50 jobs max), a searchable picker if needed. */
function JobFocus({
  jobId,
  focus,
  onChange,
  disabled,
}: {
  jobId: string | null
  focus?: { title: string | null; company: string | null } | null
  onChange: (jobId: string | null) => void
  disabled?: boolean
}) {
  const t = useT()
  const jobs = useJobs()
  const list = jobs.data ?? []
  const found = list.find((j) => j.id === jobId)
  const title = focus?.title ?? found?.data.title
  const company = focus?.company ?? found?.data.company.name
  return (
    <div className="flex flex-wrap items-center gap-2 border-b px-6 py-2 text-sm">
      {jobId ? (
        <span className="inline-flex items-center gap-2 rounded-full border bg-card py-1 pr-1 pl-3">
          <Briefcase className="size-3.5 text-primary" aria-hidden />
          <span>
            {t('coach.focus.on')} <strong>{title ?? t('coach.focus.this_job')}</strong>
            {company && ` · ${company}`}
          </span>
          <button
            type="button"
            aria-label={t('coach.focus.remove')}
            disabled={disabled}
            className="rounded-full p-1 hover:bg-accent"
            onClick={() => onChange(null)}
          >
            <X className="size-3.5" />
          </button>
        </span>
      ) : (
        <span className="text-muted-foreground">{t('coach.focus.none')}</span>
      )}
      {list.length > 0 && (
        <select
          aria-label={t('coach.focus.select_aria')}
          value=""
          disabled={disabled}
          onChange={(e) => e.target.value && onChange(e.target.value)}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="">{jobId ? t('coach.focus.switch') : t('coach.focus.choose')}</option>
          {list
            .filter((j) => j.id !== jobId)
            .map((j) => (
              <option key={j.id} value={j.id}>
                {j.data.title} · {companyOf(j)}
              </option>
            ))}
        </select>
      )}
    </div>
  )
}

/** The home screen: the career coach. `/` starts a chat; `/chat/:conversationId` reopens one. */
export function ChatPage() {
  const t = useT()
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const profile = useProfile()
  const history = useMessages(conversationId)
  const conversation = useConversation(conversationId)
  const setFocus = useSetFocus(conversationId)
  const [params] = useSearchParams()
  // `/?job=<id>` ("Discuss this job"): the job to focus a new chat on.
  const [draftJob, setDraftJob] = useState<string | null>(params.get('job'))
  const focusJob = conversationId ? (conversation.data?.job_id ?? null) : draftJob
  // `/?ask=…` (from the tracker) prefills the box; the user reviews it and sends.
  const [text, setText] = useState(params.get('ask') ?? '')
  const [pending, setPending] = useState<Pending>()
  const [error, setError] = useState<unknown>()
  const end = useRef<HTMLDivElement>(null)
  const abort = useRef<AbortController>(undefined)

  useEffect(() => () => abort.current?.abort(), [])
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' }) // may return a Promise: never return it
  }, [history.data, pending])

  /** Run one streamed turn. `start` posts to the right endpoint; nothing is stored unless the
   *  reply completes, so on a failure or a stop the user's text goes back in the box. */
  const run = async (
    user: string,
    replacing: boolean,
    start: (id: string, onEvent: OnEvent, signal: AbortSignal) => Promise<void>,
  ) => {
    if (pending) return
    setError(undefined)
    setPending({ user, assistant: '', steps: [], citations: [], notices: [], replacing })
    abort.current = new AbortController()
    try {
      const id = conversationId ?? (await createConversation(draftJob ?? undefined)).id
      await start(
        id,
        (name, data) => setPending((p) => p && applyEvent(p, name, data)),
        abort.current.signal,
      )
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['messages', id] }),
        qc.invalidateQueries({ queryKey: ['conversations'] }),
      ])
      setPending(undefined)
      if (!conversationId) navigate(`/chat/${id}`, { replace: true })
    } catch (e) {
      setPending(undefined)
      if (!replacing) setText(user)
      if (!abort.current?.signal.aborted) setError(e) // a stop is not an error
    }
  }

  const send = async (content: string) => {
    if (!content.trim()) return
    setText('')
    await run(content, false, (id, onEvent, signal) => streamMessage(id, content, onEvent, signal))
  }

  const regenerate = (userText: string) =>
    conversationId &&
    void run(userText, true, (id, onEvent, signal) => regenerateReply(id, onEvent, signal))

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
          title={t('coach.cv.title')}
          description={t('coach.cv.description')}
          action={
            <Link to="/profile" className={buttonVariants()}>
              {t('coach.cv.upload')}
            </Link>
          }
        />
      </div>
    )

  const all = history.data ?? []
  const shown = pending?.replacing ? all.slice(0, -2) : all
  const lastUser = [...all].reverse().find((m) => m.role === 'user')?.content
  const empty = shown.length === 0 && !pending && !history.isLoading

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center border-b px-6">
        <h1 className="text-lg font-semibold tracking-tight">{t('coach.title')}</h1>
        {conversationId && (
          <div className="ml-auto">
            <DeleteChatButton
              id={conversationId}
              onDeleted={() => navigate('/', { replace: true })}
            />
          </div>
        )}
      </header>
      <JobFocus
        jobId={focusJob}
        focus={conversationId ? conversation.data?.focus : undefined}
        disabled={!!pending || setFocus.isPending}
        onChange={(id) => (conversationId ? setFocus.mutate(id) : setDraftJob(id))}
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-4 p-6">
          {history.isError && <ErrorMessage error={history.error} />}
          {empty && (
            <div className="space-y-6 pt-10 text-center">
              <h2 className="text-2xl font-semibold tracking-tight">{t('coach.home')}</h2>
              <Checklist />
              <div className="mx-auto grid max-w-xl gap-2 sm:grid-cols-2">
                {PROMPTS.map(({ icon: Icon, key }) => (
                  <button
                    key={key}
                    className={card}
                    onClick={() => void send(t(`coach.prompt.${key}.send` as Key))}
                  >
                    <Icon className="size-4 text-primary" />
                    {t(`coach.prompt.${key}` as Key)}
                  </button>
                ))}
                {LINKS.map(({ icon: Icon, key, to }) => (
                  <Link key={key} to={to} className={card}>
                    <Icon className="size-4 text-primary" />
                    {t(`coach.link.${key}` as Key)}
                  </Link>
                ))}
              </div>
            </div>
          )}
          {shown.map((m, i) => (
            <div key={m.id} className="space-y-2">
              {m.role === 'assistant' && m.meta && (
                <Activity
                  steps={stepsFromMeta(m.meta, t)}
                  context={m.meta.context as Context}
                  queries={m.meta.queries}
                  citations={m.meta.citations}
                  notices={m.meta.degraded}
                />
              )}
              <Bubble role={m.role}>{m.content}</Bubble>
              {m.role === 'assistant' && m.meta && (
                <Sources
                  citations={m.meta.citations ?? []}
                  suggestionsHtml={m.meta.search_suggestions_html}
                />
              )}
              {i === shown.length - 1 && m.role === 'assistant' && !pending && lastUser && (
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => regenerate(lastUser)}
                >
                  <RefreshCw className="size-3" aria-hidden />
                  {t('coach.regenerate')}
                </button>
              )}
            </div>
          ))}
          {pending && !pending.replacing && <Bubble role="user">{pending.user}</Bubble>}
          {pending && (
            <div className="space-y-2">
              <Activity
                running={!pending.assistant}
                steps={pending.steps}
                context={pending.context}
                citations={pending.citations}
                notices={pending.notices}
              />
              {pending.assistant && (
                <Bubble role="assistant" streaming>
                  {pending.assistant}
                </Bubble>
              )}
              <Sources citations={pending.citations} suggestionsHtml={pending.suggestions} />
            </div>
          )}
          {error != null && <ErrorMessage error={error} />}
          <div ref={end} />
        </div>
      </div>
      <form onSubmit={submit} className="shrink-0 border-t bg-background p-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border bg-card p-2 shadow-xs focus-within:ring-3 focus-within:ring-ring/40">
          <textarea
            aria-label={t('coach.message_aria')}
            rows={1}
            value={text}
            maxLength={MAX}
            placeholder={t('coach.placeholder')}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none [field-sizing:content]"
          />
          {pending ? (
            <Button
              type="button"
              size="icon"
              variant="outline"
              aria-label={t('coach.stop')}
              onClick={() => abort.current?.abort()}
            >
              <Square />
            </Button>
          ) : (
            <Button type="submit" size="icon" aria-label={t('coach.send')} disabled={!text.trim()}>
              <SendHorizontal />
            </Button>
          )}
        </div>
      </form>
    </div>
  )
}
