import { Link } from 'react-router'
import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useProfile } from '@/features/candidate/api'
import type { Letter } from '@/features/letters/api'
import { useT } from '@/i18n'
import { useSetLetterSignature, useSignature } from './api'
import { fit } from './fit'
import { SigBlock } from './SigBlock'

/** Put the stored signature above the name on this letter, at a width that prints well. */
export function SignaturePanel({ letter }: { letter: Letter }) {
  const t = useT()
  const sig = useSignature()
  const profile = useProfile()
  const set = useSetLetterSignature(letter.id)
  const saved = letter.content.signature_image?.width_mm ?? null
  const [width, setWidth] = useState<number | null>(null)
  const s = sig.data
  const w = width ?? saved ?? s?.recommended_width_mm ?? 0
  const f = s ? fit(w, s.aspect, s.width_px, s.limits) : null
  const commit = (mm: number | null) => set.mutate(mm)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('signature.panel.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorMessage error={sig.error} />
        {sig.isSuccess && !s && (
          <p className="text-sm text-muted-foreground">
            {t('signature.panel.none')}{' '}
            <Link to="/profile" className="underline">
              {t('signature.panel.go')}
            </Link>
          </p>
        )}
        {s && f && (
          <>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={saved !== null}
                disabled={set.isPending}
                onChange={(e) => commit(e.target.checked ? w : null)}
              />
              {t('signature.panel.toggle')}
            </label>
            {saved !== null && (
              <>
                <label className="flex flex-wrap items-center gap-2 text-sm">
                  {t('signature.panel.width', { mm: w })}
                  <input
                    type="range"
                    min={s.limits.min_width_mm}
                    max={s.limits.max_width_mm}
                    step={1}
                    value={w}
                    onChange={(e) => setWidth(Number(e.target.value))}
                    onPointerUp={() => w !== saved && commit(w)}
                    onKeyUp={() => w !== saved && commit(w)}
                  />
                </label>
                <SigBlock
                  sig={s}
                  widthMm={f.printedWidthMm}
                  name={profile.data?.data.personal_info.name}
                />
                <ul className="space-y-1">
                  {f.alerts.map((a) => (
                    <li key={a} role="alert" className="text-sm text-destructive">
                      {t(`signature.panel.${a}`)}
                    </li>
                  ))}
                  {f.shrunk && (
                    <li className="text-sm text-muted-foreground">
                      {t('signature.panel.shrink', { mm: Math.round(f.printedWidthMm) })}
                    </li>
                  )}
                </ul>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={set.isPending}
                  onClick={() => {
                    setWidth(s.recommended_width_mm)
                    commit(s.recommended_width_mm)
                  }}
                >
                  {t('signature.panel.fit')}
                </Button>
                <p role="status" className="text-xs text-muted-foreground">
                  {t('signature.panel.rerender')}
                </p>
              </>
            )}
          </>
        )}
        <ErrorMessage error={set.error} />
      </CardContent>
    </Card>
  )
}
