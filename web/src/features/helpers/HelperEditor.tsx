import '@/features/helpers/lib'
import { Check, CircleDot, History, RotateCcw, Save, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router'
import { useI18n, useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/lib/toast'
import {
  type AgentDetail,
  isConflict,
  useAddVersion,
  useAgent,
  useAgentVersions,
  useFetchAgent,
  usePatchAgent,
} from './api'
import { AvatarPicker, SpecForm, TryPanel } from './HelperForm'
import { clearDraft, loadDraft, relTime, saveDraft } from './lib'
import { ConflictBanner, LeaveGuard, SectionCard } from './ui'
import { type AvatarSpec, safe } from './avatar'
import type { VersionSpec } from './graph'

type Fields = { name: string; description: string; avatar: AvatarSpec; spec: VersionSpec }
type Kept = Fields & { base: number }
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

export function HelperEditor() {
  const t = useT()
  const { agentId } = useParams()
  const agent = useAgent(agentId)
  return (
    <Page
      title={agent.data?.name ?? t('helpers.title')}
      back={{ to: '/helpers', label: t('helpers.back') }}
      wide
    >
      {agent.isPending ? (
        <ListSkeleton />
      ) : agent.error ? (
        <ErrorMessage error={agent.error} />
      ) : (
        <Editor key={agent.data.id} detail={agent.data} />
      )}
    </Page>
  )
}

function Editor({ detail }: { detail: AgentDetail }) {
  const { t, locale } = useI18n()
  const key = `helper-draft:${detail.id}`
  const fieldsOf = (k: Kept): Fields => ({
    name: k.name,
    description: k.description,
    avatar: k.avatar,
    spec: k.spec,
  })
  // What the server holds, as far as this editor knows. Moves only when a save succeeds (or the
  // user accepts the latest after a conflict), so "unsaved changes" is never a stale comparison.
  const [baseline, setBaseline] = useState<Kept>({
    name: detail.name,
    description: detail.description,
    avatar: detail.avatar,
    spec: detail.spec,
    base: detail.current_version,
  })
  const [draft, setDraft] = useState<Fields>(() => {
    const kept = loadDraft<Kept>(key)
    return kept && kept.base === baseline.base && !same(fieldsOf(kept), fieldsOf(baseline))
      ? fieldsOf(kept)
      : fieldsOf(baseline)
  })
  const [conflict, setConflict] = useState(false)
  const [showVersions, setShowVersions] = useState(false)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const add = useAddVersion()
  const patch = usePatchAgent()
  const fetchAgent = useFetchAgent()
  const versions = useAgentVersions(showVersions ? detail.id : undefined)

  const dirty = !same(draft, fieldsOf(baseline))
  useEffect(() => {
    if (dirty) saveDraft(key, { ...draft, base: baseline.base })
    else clearDraft(key)
  }, [dirty, draft, baseline.base, key])
  const leaving = useRef(false) // raised just before a deliberate reload

  const save = async () => {
    if (saving) return
    setSaving(true)
    setConflict(false)
    try {
      let base = baseline.base
      if (
        draft.name !== baseline.name ||
        draft.description !== baseline.description ||
        !same(draft.avatar, baseline.avatar)
      ) {
        await patch.mutateAsync({
          id: detail.id,
          body: { name: draft.name, description: draft.description, avatar: safe(draft.avatar) },
        })
      }
      if (!same(draft.spec, baseline.spec)) {
        const v = await add.mutateAsync({ id: detail.id, basedOn: base, spec: draft.spec, note })
        base = v.version
      }
      setBaseline({ ...draft, base })
      setNote('')
      clearDraft(key)
      toast(t('helpers.saved'))
    } catch (e) {
      if (isConflict(e)) setConflict(true)
    } finally {
      setSaving(false)
    }
  }
  const error = add.error ?? patch.error
  const busy = saving

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="min-w-0 space-y-5">
        <SectionCard
          icon={UserRound}
          title={t('helpers.ui.sec.identity')}
          help={t('helpers.ui.sec.identity_help')}
        >
          <AvatarPicker
            value={draft.avatar}
            onChange={(avatar) => setDraft({ ...draft, avatar })}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="h-name">{t('helpers.name')}</Label>
              <Input
                id="h-name"
                value={draft.name}
                maxLength={80}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="h-desc">{t('helpers.goal')}</Label>
              <Input
                id="h-desc"
                value={draft.description}
                maxLength={200}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </div>
          </div>
          <p className="font-mono text-xs text-muted-foreground">
            {t('helpers.id')}: {detail.id}
          </p>
        </SectionCard>

        <SpecForm spec={draft.spec} onChange={(spec) => setDraft({ ...draft, spec })} />

        <div className="sticky bottom-4 z-10 flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border bg-card/95 p-3 shadow-lg backdrop-blur">
          <span role="status" className="flex items-center gap-2 text-sm">
            {dirty ? (
              <>
                <CircleDot className="size-4 text-warning" aria-hidden />
                {t('helpers.unsaved')}
              </>
            ) : (
              <>
                <Check className="size-4 text-success" aria-hidden />
                <span className="text-muted-foreground">{t('helpers.ui.saved_state')}</span>
              </>
            )}
          </span>
          <span className="flex-1" />
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium tabular-nums">
            v{baseline.base}
          </span>
          <Button
            variant="outline"
            onClick={() => setShowVersions((s) => !s)}
            aria-expanded={showVersions}
          >
            <History data-icon="inline-start" />
            {t('helpers.versions')}
          </Button>
          <Button onClick={save} disabled={!dirty || busy || !draft.name.trim()}>
            {busy ? <Spinner /> : <Save data-icon="inline-start" />}
            {t('helpers.save_version')}
          </Button>
          {dirty && (
            <Input
              aria-label={t('helpers.note')}
              placeholder={t('helpers.note')}
              className="order-last basis-full"
              maxLength={200}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          )}
        </div>
        <ErrorMessage error={conflict ? null : error} />
        {conflict && (
          <ConflictBanner
            onReload={() => {
              clearDraft(key)
              leaving.current = true // a deliberate reload must not ask again
              window.location.reload()
            }}
            onKeep={async () => {
              // build on what the server has now, so the next save is not refused again
              const fresh = await fetchAgent(detail.id)
              setBaseline((b) => ({ ...b, base: fresh.current_version }))
              setConflict(false)
            }}
          />
        )}

        {showVersions && (
          <section
            aria-label={t('helpers.versions')}
            className="rounded-xl border bg-card p-5 shadow-xs"
          >
            {versions.isPending ? (
              <ListSkeleton rows={2} />
            ) : (
              <ol className="relative space-y-4 border-l pl-5">
                {(versions.data ?? []).map((v) => (
                  <li key={v.id} className="relative flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span
                      aria-hidden
                      className={`absolute top-1.5 -left-[25px] size-2 rounded-full ring-4 ring-card ${v.version === baseline.base ? 'bg-primary' : 'bg-border'}`}
                    />
                    <span className="font-medium tabular-nums">v{v.version}</span>
                    {v.version === baseline.base && (
                      <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground">
                        {t('helpers.ui.current')}
                      </span>
                    )}
                    <time
                      dateTime={v.created_at}
                      title={new Date(v.created_at).toLocaleString(locale)}
                      className="text-sm text-muted-foreground"
                    >
                      {relTime(v.created_at, locale)}
                    </time>
                    <span className="order-last basis-full text-sm text-muted-foreground italic">
                      {v.note || t('helpers.ui.no_note')}
                    </span>
                    <span className="flex-1" />
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() => setDraft({ ...draft, spec: v.spec })}
                    >
                      <RotateCcw data-icon="inline-start" />
                      {t('helpers.restore')}
                    </Button>
                  </li>
                ))}
              </ol>
            )}
          </section>
        )}
      </div>

      <div className="lg:sticky lg:top-20 lg:self-start">
        <TryPanel agentId={detail.id} spec={draft.spec} />
      </div>

      <LeaveGuard dirty={dirty} leaving={leaving} />
    </div>
  )
}
