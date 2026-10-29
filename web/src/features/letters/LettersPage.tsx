import { FileText } from 'lucide-react'
import { jobLabel } from '@/features/job-search/label'
import { useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { StepProgress } from '@/components/StepProgress'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { LANG_NAMES, LANGS, useI18n, type Lang } from '@/i18n'
import { useJobs } from '@/features/job-search/api'
import { DeleteLetterButton } from './DeleteLetterButton'
import { MotivationBlock } from './MotivationBlock'
import { useCreateLetter, useLetters, type LetterIn } from './api'

const OPTIONS = {
  language: LANGS,
  tone: ['professional', 'warm', 'confident', 'academic', 'formal'],
  length: ['short', 'standard', 'detailed'],
  company_type: ['corporate', 'startup', 'phd'],
  template: ['classic', 'modern', 'compact', 'lettre_fr'],
} as const

function NewLetter() {
  const { t, lang } = useI18n()
  const optionLabel = (k: keyof typeof OPTIONS, o: string) =>
    k === 'language'
      ? LANG_NAMES[o as Lang]
      : t(`letters.${k === 'company_type' ? 'company' : k}.${o}` as never)
  const steps = [t('letters.new.step1'), t('letters.new.step2'), t('letters.new.step3')]
  const jobs = useJobs()
  const create = useCreateLetter()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { register, handleSubmit, control, setValue } = useForm<LetterIn>({
    defaultValues: {
      job_id: params.get('job') ?? '',
      highlights: [],
      motivation: '',
      answers: [],
      mode: 'ai',
      language: lang,
      tone: 'professional',
      length: 'standard',
      company_type: 'corporate',
      template: 'classic',
    },
  })
  const [jobId, highlights, motivation, mode, language] = useWatch({
    control,
    name: ['job_id', 'highlights', 'motivation', 'mode', 'language'],
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('letters.new.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        {jobs.data?.length === 0 ? (
          <p className="text-muted-foreground">
            {t('letters.new.no_jobs').split('{link}')[0]}
            <Link
              to="/jobs"
              className="underline pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:items-center"
            >
              {t('letters.new.jobs_link')}
            </Link>
            {t('letters.new.no_jobs').split('{link}')[1]}
          </p>
        ) : (
          <form
            className="grid gap-3 sm:grid-cols-3"
            onSubmit={handleSubmit((v) =>
              create.mutate(
                { ...v, answers: (v.answers ?? []).filter((a) => a.answer.trim()) },
                { onSuccess: (l) => navigate(`/letters/${l.id}`) },
              ),
            )}
          >
            <div className="space-y-1 sm:col-span-3">
              <Label htmlFor="job_id">{t('letters.new.job')}</Label>
              <NativeSelect
                id="job_id"
                className="w-full"
                {...register('job_id', {
                  required: true,
                  // The answers belong to one job: never carry them over to another.
                  onChange: () => {
                    setValue('answers', [])
                    setValue('highlights', [])
                  },
                })}
              >
                <NativeSelectOption value="" disabled>
                  {t('letters.new.choose_job')}
                </NativeSelectOption>
                {jobs.data?.map((j) => (
                  <NativeSelectOption key={j.id} value={j.id}>
                    {jobLabel(j)}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            {(Object.keys(OPTIONS) as (keyof typeof OPTIONS)[]).map((k) => (
              <div className="space-y-1" key={k}>
                <Label htmlFor={k}>{t(`letters.new.${k}`)}</Label>
                <NativeSelect id={k} className="w-full" {...register(k)}>
                  {OPTIONS[k].map((o) => (
                    <NativeSelectOption key={o} value={o}>
                      {optionLabel(k, o)}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </div>
            ))}
            <fieldset className="space-y-1 sm:col-span-3">
              <legend className="text-sm font-medium">{t('letters.new.who')}</legend>
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    ['ai', t('letters.new.mode_ai'), t('letters.new.mode_ai_hint')],
                    ['own_words', t('letters.new.mode_own'), t('letters.new.mode_own_hint')],
                  ] as const
                ).map(([value, title, hint]) => (
                  <label
                    key={value}
                    className="flex min-w-48 flex-1 cursor-pointer items-start gap-2 rounded-lg border p-3 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"
                  >
                    <input type="radio" value={value} className="mt-1" {...register('mode')} />
                    <span>
                      <span className="block font-medium">{title}</span>
                      <span className="text-muted-foreground">{hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <MotivationBlock
              key={`${jobId}-${language}`}
              own={mode === 'own_words'}
              jobId={jobId}
              language={language ?? lang}
              highlights={highlights ?? []}
              note={motivation ?? ''}
              onHighlights={(v) => setValue('highlights', v)}
              onNote={(v) => setValue('motivation', v)}
              onAnswers={(v) => setValue('answers', v)}
            />
            {create.isPending && (
              <div className="sm:col-span-3">
                <StepProgress steps={steps} />
              </div>
            )}
            {create.isError && <ErrorMessage error={create.error} />}
            <Button type="submit" className="sm:w-fit" loading={create.isPending}>
              {create.isPending
                ? t('letters.new.preparing')
                : mode === 'own_words'
                  ? t('letters.new.create_own')
                  : t('letters.new.generate')}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  )
}

export function LettersPage() {
  const { t, locale } = useI18n()
  const letters = useLetters()
  return (
    <Page title={t('letters.title')} description={t('letters.description')}>
      <NewLetter />
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground">{t('letters.your_letters')}</h2>
        {letters.isPending && <ListSkeleton rows={2} />}
        {letters.isError && <ErrorMessage error={letters.error} />}
        {letters.data?.length === 0 && (
          <EmptyState
            icon={FileText}
            title={t('letters.empty.title')}
            description={t('letters.empty.description')}
          />
        )}
        <ul className="space-y-2">
          {letters.data?.map((l) => (
            <li
              key={l.id}
              className="flex items-center gap-2 rounded-xl border bg-card shadow-xs transition-colors hover:bg-accent/50"
            >
              <Link to={`/letters/${l.id}`} className="block min-w-0 flex-1 p-4">
                <p className="font-medium">{l.content.subject || t('letters.untitled')}</p>
                <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                  <StatusBadge tone="info">{LANG_NAMES[l.language]}</StatusBadge>
                  <StatusBadge>{t(`letters.tone.${l.tone}`)}</StatusBadge>
                  {new Date(l.updated_at).toLocaleDateString(locale)}
                </p>
              </Link>
              <div className="pr-4">
                <DeleteLetterButton id={l.id} />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </Page>
  )
}
