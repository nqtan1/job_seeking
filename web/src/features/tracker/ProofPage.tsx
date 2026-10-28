import { useState } from 'react'
import { useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useProof } from './api'
import { sourceLabel } from './constants'
import { toCsv } from './csv'

const STEPS = ['applied', 'in_review', 'interview', 'offer', 'rejected']

const thisMonth = () => new Date().toISOString().slice(0, 7)

/** The user's own record of a month's search steps, from the tracker. Nothing is sent anywhere:
 *  they download it or print it (browser "Save as PDF") to keep or show if asked. */
export function ProofPage() {
  const t = useT()
  const step = (s: string) =>
    STEPS.includes(s) ? t(`tracker.proof.step_${s}` as 'tracker.proof.step_offer') : s
  const [month, setMonth] = useState(thisMonth)
  const proof = useProof(month)
  const rows = proof.data?.rows ?? []

  const download = () => {
    const csv = toCsv([
      [
        t('tracker.proof.date'),
        t('tracker.proof.company'),
        t('tracker.proof.job'),
        t('tracker.proof.source'),
        t('tracker.proof.step'),
      ],
      ...rows.map((r) => [
        r.at.slice(0, 10),
        r.company_name,
        r.job_title,
        sourceLabel(t, r.source),
        step(r.step),
      ]),
    ])
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const a = Object.assign(document.createElement('a'), {
      href: url,
      download: `search-${month}.csv`,
    })
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Page
      title={t('tracker.proof.title')}
      description={t('tracker.proof.description')}
      back={{ to: '/tracker', label: t('tracker.proof.back') }}
      actions={
        <div className="flex gap-2 print:hidden">
          <Button size="sm" variant="outline" disabled={rows.length === 0} onClick={download}>
            {t('tracker.proof.csv')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={rows.length === 0}
            onClick={() => window.print()}
          >
            {t('tracker.proof.print')}
          </Button>
        </div>
      }
    >
      <div className="space-y-1 print:hidden">
        <Label htmlFor="month">{t('tracker.proof.month')}</Label>
        <Input
          id="month"
          type="month"
          className="w-48"
          value={month}
          max={thisMonth()}
          onChange={(e) => e.target.value && setMonth(e.target.value)}
        />
      </div>
      {proof.isPending && <ListSkeleton rows={3} />}
      {proof.isError && <ErrorMessage error={proof.error} />}
      {proof.data && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('tracker.proof.none')}</p>
      )}
      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-4 font-medium">{t('tracker.proof.date')}</th>
              <th className="py-2 pr-4 font-medium">{t('tracker.proof.company')}</th>
              <th className="py-2 pr-4 font-medium">{t('tracker.proof.job')}</th>
              <th className="py-2 font-medium">{t('tracker.proof.step')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b">
                <td className="py-2 pr-4 tabular-nums">{r.at.slice(0, 10)}</td>
                <td className="py-2 pr-4">{r.company_name}</td>
                <td className="py-2 pr-4">{r.job_title ?? ''}</td>
                <td className="py-2">{step(r.step)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Page>
  )
}
