import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StepProgress } from '@/components/StepProgress'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { useI18n, type Key } from '@/i18n'
import { uploadDocument } from '@/lib/api/documents'
import {
  LEVELS,
  TRACKS,
  useCvDocuments,
  useDeleteReview,
  useReview,
  useReviewRun,
  useReviews,
  type Level,
  type Track,
} from './api'
import { ReviewView } from './ReviewView'

function Start() {
  const { t, locale } = useI18n()
  const qc = useQueryClient()
  const docs = useCvDocuments()
  const [doc, setDoc] = useState('')
  const [track, setTrack] = useState<Track>('backend')
  const [level, setLevel] = useState<Level>('mid')
  const upload = useMutation({
    mutationFn: (f: File) => uploadDocument('cv', f),
    onSuccess: async (id) => {
      await qc.invalidateQueries({ queryKey: ['documents', 'cv'] })
      setDoc(id)
    },
  })
  const { run, running, error } = useReviewRun()
  const list = [...(docs.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))
  const documentId = doc || list[0]?.document_id || ''
  const picks: [string, string, string, (v: string) => void, string[][]][] = [
    [
      'cvr-doc',
      t('cvr.cv'),
      documentId,
      setDoc,
      list.map((d) => [
        d.document_id,
        `${new Date(d.created_at).toLocaleDateString(locale)} · ${Math.max(1, Math.round(d.size / 1024))} KB`,
      ]),
    ],
    [
      'cvr-track',
      t('cvr.track'),
      track,
      (v) => setTrack(v as Track),
      TRACKS.map((v) => [v, t(`cvr.track.${v}` as Key)]),
    ],
    [
      'cvr-level',
      t('cvr.level'),
      level,
      (v) => setLevel(v as Level),
      LEVELS.map((v) => [v, t(`cvr.level.${v}` as Key)]),
    ],
  ]

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          {picks.map(([id, label, value, onChange, options]) => (
            <div key={id} className="space-y-1">
              <Label htmlFor={id}>{label}</Label>
              <NativeSelect
                id={id}
                className="w-full"
                value={value}
                onChange={(e) => onChange(e.target.value)}
              >
                {options.map(([v, text]) => (
                  <NativeSelectOption key={v} value={v}>
                    {text}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
          ))}
        </div>
        {!docs.isPending && list.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('cvr.no_cv')}</p>
        )}
        <div className="space-y-1">
          <Label htmlFor="cvr-upload">{t('cvr.upload')}</Label>
          <Input
            id="cvr-upload"
            type="file"
            accept=".pdf,.docx"
            onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])}
          />
        </div>
        <Button
          disabled={!documentId}
          loading={running}
          onClick={() => run({ document_id: documentId, track, level })}
        >
          {t('cvr.start')}
        </Button>
        {running && (
          <StepProgress steps={[t('cvr.step_read'), t('cvr.step_check'), t('cvr.step_write')]} />
        )}
        <ErrorMessage error={docs.error ?? upload.error ?? error} />
      </CardContent>
    </Card>
  )
}

function History() {
  const { t, locale } = useI18n()
  const list = useReviews()
  const del = useDeleteReview()
  if (list.isPending) return <ListSkeleton />
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('cvr.history')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <ErrorMessage error={list.error ?? del.error} />
        {list.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('cvr.history_empty')}</p>
        )}
        {list.data?.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-semibold">{Math.round(r.score)}</span>
            <span className="min-w-0 flex-1 text-muted-foreground">
              {t(`cvr.track.${r.track}` as Key)} · {t(`cvr.level.${r.level}` as Key)} ·{' '}
              {new Date(r.created_at).toLocaleDateString(locale)}
            </span>
            <Link
              to={`/cv-review/${r.id}`}
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
            >
              {t('cvr.open')}
            </Link>
            <ConfirmButton
              label={t('cvr.delete')}
              confirmLabel={t('cvr.delete_confirm')}
              variant="outline"
              pending={del.isPending}
              onConfirm={(reset) => del.mutate(r.id, { onSettled: reset })}
            />
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function Detail({ id }: { id: string }) {
  const { t } = useI18n()
  const review = useReview(id)
  const back = { to: '/cv-review', label: t('cvr.back') }
  return (
    <Page title={t('cvr.title')} back={back} wide>
      {review.isPending && <ListSkeleton />}
      <ErrorMessage error={review.error} />
      {/* Keyed by id: edits and undo never leak from one review to the next. */}
      {review.data && <ReviewView key={id} review={review.data} />}
    </Page>
  )
}

export function CvReviewPage() {
  const { t } = useI18n()
  const { reviewId } = useParams()
  if (reviewId) return <Detail id={reviewId} />
  return (
    <Page title={t('cvr.title')} description={t('cvr.desc')}>
      <Start />
      <History />
    </Page>
  )
}
