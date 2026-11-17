import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useT } from '@/i18n'
import { analyticsAvailable, getConsent, setConsent, type Consent } from '@/lib/analytics'

/** Asked once, only when analytics is built in; nothing loads until "Accept". */
export function AnalyticsBanner() {
  const t = useT()
  const [open, setOpen] = useState(() => analyticsAvailable() && getConsent() === null)
  if (!open) return null
  const choose = (c: Consent) => {
    setConsent(c)
    setOpen(false)
  }
  return (
    <section
      aria-label={t('analytics.label')}
      className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-xl flex-wrap items-center gap-3 rounded-lg border bg-background p-3 text-sm shadow-lg"
    >
      <p className="min-w-0 flex-1">
        {t('analytics.ask')}{' '}
        <a href="/privacy" className="text-primary underline">
          {t('analytics.more')}
        </a>
      </p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => choose('no')}>
          {t('analytics.decline')}
        </Button>
        <Button size="sm" onClick={() => choose('yes')}>
          {t('analytics.accept')}
        </Button>
      </div>
    </section>
  )
}

export function AnalyticsCard() {
  const t = useT()
  const [on, setOn] = useState(() => getConsent() === 'yes')
  if (!analyticsAvailable()) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('analytics.label')}</CardTitle>
        <CardDescription>{t('analytics.desc')}</CardDescription>
      </CardHeader>
      <CardContent>
        <label className="flex items-center gap-2 text-sm pointer-coarse:min-h-11">
          <input
            type="checkbox"
            className="pointer-coarse:size-5"
            checked={on}
            onChange={(e) => {
              setConsent(e.target.checked ? 'yes' : 'no')
              setOn(e.target.checked)
            }}
          />
          {t('analytics.share')}
        </label>
      </CardContent>
    </Card>
  )
}
