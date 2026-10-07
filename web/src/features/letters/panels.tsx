import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { exportLetter, useCheck, useRestore, useVersions } from './api'
import { editorBlocks } from './blocks'

export function VersionsPanel({
  letterId,
  onRestored,
}: {
  letterId: string
  onRestored: () => void
}) {
  const versions = useVersions(letterId)
  const restore = useRestore(letterId)
  const [open, setOpen] = useState<number>()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Versions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {versions.isPending && <p className="text-sm text-muted-foreground">Loading versions…</p>}
        {versions.isError && <ErrorMessage error={versions.error} />}
        {restore.isError && <ErrorMessage error={restore.error} />}
        {versions.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">No earlier versions.</p>
        )}
        {versions.data?.map((v) => (
          <div key={v.n} className="rounded-md border p-2">
            <div className="flex items-center justify-between gap-2">
              <button
                className="text-left text-sm font-medium hover:underline"
                aria-expanded={open === v.n}
                onClick={() => setOpen(open === v.n ? undefined : v.n)}
              >
                Version {v.n} · {new Date(v.created_at).toLocaleString()}
              </button>
              <Button
                size="sm"
                variant="outline"
                disabled={restore.isPending}
                aria-label={`Restore version ${v.n}`}
                onClick={() => restore.mutate(v.n, { onSuccess: onRestored })}
              >
                Restore
              </Button>
            </div>
            {open === v.n && (
              <div className="mt-2 space-y-1 text-sm text-muted-foreground">
                {editorBlocks(v.content).map((b) => (
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
  const check = useCheck(letterId)
  const q = check.data?.quality
  return (
    <Card>
      <CardHeader>
        <CardTitle>Quality check</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <Button size="sm" disabled={check.isFetching} onClick={() => check.refetch()}>
          {check.isFetching ? 'Checking…' : check.data ? 'Re-run check' : 'Run check'}
        </Button>
        {check.isError && <ErrorMessage error={check.error} />}
        {check.data && q && (
          <>
            <p>
              Length: {q.word_count} words (target {q.target_words}){' '}
              <span className={q.within_target ? 'text-primary' : 'text-destructive'}>
                {q.within_target ? 'on target' : 'off target'}
              </span>
            </p>
            <p>
              Keywords from the job covered: {q.keyword_coverage.covered.join(', ') || 'none'}
              {q.keyword_coverage.missing.length > 0 && (
                <> · missing: {q.keyword_coverage.missing.join(', ')}</>
              )}
            </p>
            {q.cliches.length > 0 && <p>Clichés: {q.cliches.join(', ')}</p>}
            {check.data.unsupported_claims.length === 0 ? (
              <p className="text-primary">Every claim is supported by your profile.</p>
            ) : (
              <div>
                <p className="font-medium text-destructive">Not found in your profile:</p>
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
  const [error, setError] = useState<unknown>()
  const download = async (format: 'text' | 'email') => {
    setError(undefined)
    try {
      const out = await exportLetter(letterId, format)
      const text = out.subject ? `Subject: ${out.subject}\n\n${out.body}` : out.body
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
      a.download = format === 'email' ? 'letter-email.txt' : 'letter.txt'
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      setError(e)
    }
  }
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => download('text')}>
          Download as text
        </Button>
        <Button size="sm" variant="outline" onClick={() => download('email')}>
          Download as email
        </Button>
      </div>
      {error != null && <ErrorMessage error={error} />}
    </div>
  )
}
