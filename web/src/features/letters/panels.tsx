import { downloadBlob } from '@/lib/download'
import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n, useT } from '@/i18n'
import { exportLetter, useCheck, useRestore, useVersions } from './api'
import { editorBlocks } from './blocks'

export function VersionsPanel({
  letterId,
  onRestored,
}: {
  letterId: string
  onRestored: () => void
}) {
  const { t, locale } = useI18n()
  const versions = useVersions(letterId)
  const restore = useRestore(letterId)
  const [open, setOpen] = useState<number>()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('letters.versions.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {versions.isPending && (
          <p className="text-sm text-muted-foreground">{t('letters.versions.loading')}</p>
        )}
        {versions.isError && <ErrorMessage error={versions.error} />}
        {restore.isError && <ErrorMessage error={restore.error} />}
        {versions.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('letters.versions.none')}</p>
        )}
        {versions.data?.map((v) => (
          <div key={v.n} className="rounded-md border p-2">
            <div className="flex items-center justify-between gap-2">
              <button
                className="text-left text-sm font-medium hover:underline"
                aria-expanded={open === v.n}
                onClick={() => setOpen(open === v.n ? undefined : v.n)}
              >
                {t('letters.versions.item', {
                  n: v.n,
                  date: new Date(v.created_at).toLocaleString(locale),
                })}
              </button>
              <Button
                size="sm"
                variant="outline"
                disabled={restore.isPending}
                aria-label={t('letters.versions.restore_aria', { n: v.n })}
                onClick={() => restore.mutate(v.n, { onSuccess: onRestored })}
              >
                {t('letters.versions.restore')}
              </Button>
            </div>
            {open === v.n && (
              <div className="mt-2 space-y-1 text-sm text-muted-foreground">
                {editorBlocks(v.content, t).map((b) => (
                  <p key={b.key}>{b.text}</p>
                ))}
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

export function QualityPanel({ letterId }: { letterId: string }) {
  const t = useT()
  const check = useCheck(letterId)
  const q = check.data?.quality
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('letters.quality.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <Button size="sm" disabled={check.isFetching} onClick={() => check.refetch()}>
          {check.isFetching
            ? t('letters.quality.checking')
            : check.data
              ? t('letters.quality.rerun')
              : t('letters.quality.run')}
        </Button>
        {check.isError && <ErrorMessage error={check.error} />}
        {check.data && q && (
          <>
            <p>
              {t('letters.quality.length', { words: q.word_count, target: q.target_words })}{' '}
              <span className={q.within_target ? 'text-primary' : 'text-destructive'}>
                {q.within_target ? t('letters.quality.on_target') : t('letters.quality.off_target')}
              </span>
            </p>
            <p>
              {t('letters.quality.keywords', {
                list: q.keyword_coverage.covered.join(', ') || t('letters.quality.none'),
              })}
              {q.keyword_coverage.missing.length > 0 && (
                <>
                  {' · '}
                  {t('letters.quality.missing', { list: q.keyword_coverage.missing.join(', ') })}
                </>
              )}
            </p>
            {q.cliches.length > 0 && (
              <p>{t('letters.quality.cliches', { list: q.cliches.join(', ') })}</p>
            )}
            {check.data.unsupported_claims.length === 0 ? (
              <p className="text-primary">{t('letters.quality.supported')}</p>
            ) : (
              <div>
                <p className="font-medium text-destructive">{t('letters.quality.unsupported')}</p>
                <ul className="list-disc pl-5">
                  {check.data.unsupported_claims.map((c) => (
                    <li key={`${c.term}-${c.sentence}`}>
                      <strong>{c.term}</strong> ({c.kind}): “{c.sentence}”
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

export function ExportButtons({ letterId }: { letterId: string }) {
  const t = useT()
  const [error, setError] = useState<unknown>()
  const download = async (format: 'text' | 'email') => {
    setError(undefined)
    try {
      const out = await exportLetter(letterId, format)
      const text = out.subject
        ? `${t('letters.export.subject', { subject: out.subject })}\n\n${out.body}`
        : out.body
      downloadBlob(
        format === 'email' ? 'letter-email.txt' : 'letter.txt',
        'text/plain;charset=utf-8',
        text,
      )
    } catch (e) {
      setError(e)
    }
  }
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => download('text')}>
          {t('letters.export.text')}
        </Button>
        <Button size="sm" variant="outline" onClick={() => download('email')}>
          {t('letters.export.email')}
        </Button>
      </div>
      {error != null && <ErrorMessage error={error} />}
    </div>
  )
}
