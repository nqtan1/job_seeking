import { ContractPicker } from '@/components/ContractPicker'
import { PlacePicker } from '@/components/PlacePicker'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { StepProgress } from '@/components/StepProgress'
import { X } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useT } from '@/i18n'
import { JobList } from './JobList'
import {
  MAX_FILES,
  useAddJob,
  useAddJobFiles,
  useParseQuery,
  useSearchJobs,
  type SearchParams,
} from './api'

function ManualEntry({ add }: { add: ReturnType<typeof useAddJob> }) {
  const t = useT()
  const { register, handleSubmit, reset, formState } = useForm<{ text: string }>()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('jobs.paste_title')}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-3"
          onSubmit={handleSubmit(({ text }) => add.mutate({ text }, { onSuccess: () => reset() }))}
        >
          <Label htmlFor="jd-text">{t('jobs.paste_label')}</Label>
          <Textarea id="jd-text" rows={6} {...register('text', { required: true })} />
          {formState.errors.text && (
            <p role="alert" className="text-sm text-destructive">
              {t('jobs.paste_required')}
            </p>
          )}
          <Button type="submit" loading={add.isPending}>
            {add.isPending ? t('jobs.analysing') : t('jobs.add_job')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

const ACCEPT =
  '.pdf,.docx,.txt,.png,.jpg,.jpeg,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,image/png,image/jpeg'
// Keep in step with ACCEPT and the backend allowlist (documents/service.py). Dropped files
// bypass the dialog's `accept`, so they are checked here; a screenshot may have no extension.
const ALLOWED_NAME = /\.(pdf|docx|txt|png|jpe?g)$/i
const ALLOWED_TYPE = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'image/png',
  'image/jpeg',
])
const isAllowed = (f: File) => ALLOWED_NAME.test(f.name) || ALLOWED_TYPE.has(f.type)
const fileKey = (f: File) => `${f.name}|${f.size}|${f.lastModified}`

function FileEntry() {
  const t = useT()
  const steps = useSteps()
  const add = useAddJobFiles()
  const [files, setFiles] = useState<File[]>([])
  const [skipped, setSkipped] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)
  const tooMany = files.length > MAX_FILES

  // Every pick (dialog or drop) ADDS to the batch: the user builds it up in as many picks as
  // they like; a file already in the batch is not added twice.
  const addFiles = (picked: File[]) => {
    const ok = picked.filter(isAllowed)
    setSkipped(picked.filter((f) => !isAllowed(f)).map((f) => f.name))
    setFiles((cur) => {
      const seen = new Set(cur.map(fileKey))
      return [...cur, ...ok.filter((f) => !seen.has(fileKey(f)))]
    })
    add.reset()
  }
  const clear = () => {
    setFiles([])
    setSkipped([])
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('jobs.upload_title')}</CardTitle>
        <CardDescription>{t('jobs.upload_desc', { max: MAX_FILES })}</CardDescription>
      </CardHeader>
      <CardContent
        className={`space-y-3 transition-colors ${dragging ? 'bg-accent/40' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={(e) => {
          // Moving over a child fires dragleave too: only a real exit ends the highlight.
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false)
        }}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          addFiles([...e.dataTransfer.files])
        }}
      >
        <Label htmlFor="jd-file">{t('jobs.upload_label')}</Label>
        <Input
          id="jd-file"
          type="file"
          multiple
          accept={ACCEPT}
          onChange={(e) => {
            addFiles([...(e.target.files ?? [])])
            e.target.value = '' // so choosing the same file again still fires onChange
          }}
        />
        <p className="text-xs text-muted-foreground">{t('jobs.upload_hint')}</p>
        {files.length > 0 && (
          <ul className="space-y-1 text-sm">
            {files.map((f) => (
              <li key={fileKey(f)} className="flex items-center justify-between gap-2">
                <span className="truncate">{f.name}</span>
                <Button
                  size="icon-xs"
                  variant="ghost"
                  aria-label={t('jobs.remove_aria', { name: f.name })}
                  disabled={add.isPending}
                  onClick={() => setFiles((cur) => cur.filter((x) => x !== f))}
                >
                  <X />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {skipped.length > 0 && (
          <p role="alert" className="text-sm text-destructive">
            {t('jobs.skipped', { names: skipped.join(', ') })}
          </p>
        )}
        {tooMany && (
          <p role="alert" className="text-sm text-destructive">
            {t('jobs.too_many', { max: MAX_FILES, extra: files.length - MAX_FILES })}
          </p>
        )}
        {add.isPending && <StepProgress steps={steps} />}
        {add.isError && <ErrorMessage error={add.error} />}
        <div className="flex items-center gap-2">
          <Button
            loading={add.isPending}
            disabled={files.length === 0 || tooMany}
            onClick={() =>
              add.mutate(files, {
                onSuccess: clear,
              })
            }
          >
            {add.isPending ? t('jobs.analysing') : t('jobs.upload_add')}
          </Button>
          {files.length > 0 && !add.isPending && (
            <Button variant="ghost" onClick={clear}>
              {t('jobs.clear')}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function Search({ add }: { add: ReturnType<typeof useAddJob> }) {
  const [params, setParams] = useState<SearchParams>()
  const search = useSearchJobs(params)
  const { register, handleSubmit, control, setValue } = useForm<SearchParams>()
  const parse = useParseQuery()
  const [sentence, setSentence] = useState('')
  const t = useT()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('jobs.search_title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <Label htmlFor="sentence">{t('jobs.describe_label')}</Label>
          <div className="flex gap-2">
            <Input
              id="sentence"
              value={sentence}
              maxLength={300}
              placeholder={t('jobs.describe_placeholder')}
              onChange={(e) => setSentence(e.target.value)}
            />
            <Button
              type="button"
              variant="outline"
              disabled={parse.isPending || sentence.trim().length < 3}
              onClick={() =>
                parse.mutate(sentence.trim(), {
                  onSuccess: (f) => {
                    setValue('query', f.query ?? '')
                    setValue('department', f.department ?? undefined)
                    setValue('contract_type', f.contract_type ?? undefined)
                  },
                })
              }
            >
              {parse.isPending ? t('jobs.reading') : t('jobs.fill_filters')}
            </Button>
          </div>
          {parse.isError && <ErrorMessage error={parse.error} />}
          {parse.data && (
            <p className="text-xs text-muted-foreground">
              {t('jobs.check_filters')}
              {parse.data.remote && t('jobs.remote_note')}
              {parse.data.notes.length > 0 &&
                t('jobs.not_filterable', { notes: parse.data.notes.join('; ') })}
            </p>
          )}
        </div>
        <form className="grid gap-3 sm:grid-cols-4" onSubmit={handleSubmit(setParams)}>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="q">{t('jobs.keywords')}</Label>
            <Input id="q" {...register('query')} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label>{t('jobs.where')}</Label>
            <Controller
              control={control}
              name="department"
              render={({ field }) => (
                <PlacePicker value={field.value} onChange={(v) => field.onChange(v ?? undefined)} />
              )}
            />
          </div>
          <div className="space-y-1 sm:col-span-4">
            <Label>{t('jobs.contract_types')}</Label>
            <Controller
              control={control}
              name="contract_type"
              render={({ field }) => (
                <ContractPicker
                  value={field.value}
                  onChange={(v) => field.onChange(v ?? undefined)}
                />
              )}
            />
          </div>
          <Button type="submit" className="sm:col-span-4 sm:w-fit" disabled={search.isFetching}>
            {search.isFetching ? t('jobs.searching') : t('jobs.search')}
          </Button>
        </form>
        {search.isError && <ErrorMessage error={search.error} />}
        {search.data?.results.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('jobs.no_offers')}</p>
        )}
        <ul className="max-h-96 space-y-2 overflow-y-auto pr-1">
          {search.data?.results.map((r) => (
            <li key={r.id} className="flex items-start justify-between gap-4 rounded-lg border p-3">
              <div>
                <p className="font-medium">{r.title}</p>
                <p className="text-sm text-muted-foreground">
                  {[r.company, r.location, r.contract_type_label].filter(Boolean).join(' · ')}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={add.isPending}
                aria-label={t('jobs.add_aria', { title: r.title })}
                onClick={() => add.mutate({ externalId: r.id })}
              >
                {t('jobs.add')}
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

const useSteps = () => {
  const t = useT()
  return [t('jobs.step_read'), t('jobs.step_extract')]
}

export function JobsPage() {
  const add = useAddJob()
  const t = useT()
  const steps = useSteps()
  return (
    <Page title={t('jobs.page_title')} description={t('jobs.page_desc')} wide>
      {add.isError && <ErrorMessage error={add.error} />}
      {add.isPending && <StepProgress steps={steps} />}
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-2">
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground">{t('jobs.your_jobs')}</h2>
          <JobList />
        </section>
        <div className="space-y-6">
          <Search add={add} />
          <FileEntry />
          <ManualEntry add={add} />
        </div>
      </div>
    </Page>
  )
}
