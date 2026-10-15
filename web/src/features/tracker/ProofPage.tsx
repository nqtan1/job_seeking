import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useProof } from './api'
import { toCsv } from './csv'

const STEP: Record<string, string> = {
  applied: 'Application sent',
  in_review: 'Under review',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Declined',
}

const thisMonth = () => new Date().toISOString().slice(0, 7)

/** The user's own record of a month's search steps, from the tracker. Nothing is sent anywhere:
 *  they download it or print it (browser "Save as PDF") to keep or show if asked. */
export function ProofPage() {
  const [month, setMonth] = useState(thisMonth)
  const proof = useProof(month)
  const rows = proof.data?.rows ?? []

  const download = () => {
    const csv = toCsv([
      ['Date', 'Company', 'Job', 'Source', 'Step'],
      ...rows.map((r) => [
        r.at.slice(0, 10),
        r.company_name,
        r.job_title,
        r.source.replace('_', ' '),
        STEP[r.step] ?? r.step,
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
      title="Search record"
      description="Your job-search steps for a month, taken from your tracker."
      back={{ to: '/tracker', label: 'Tracker' }}
      actions={
        <div className="flex gap-2 print:hidden">
          <Button size="sm" variant="outline" disabled={rows.length === 0} onClick={download}>
            Download CSV
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={rows.length === 0}
            onClick={() => window.print()}
          >
            Print / Save as PDF
          </Button>
        </div>
      }
    >
      <div className="space-y-1 print:hidden">
        <Label htmlFor="month">Month</Label>
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
        <p className="text-sm text-muted-foreground">
          No steps this month. Sending an application or getting an answer is recorded here
          automatically.
        </p>
      )}
      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-4 font-medium">Date</th>
              <th className="py-2 pr-4 font-medium">Company</th>
              <th className="py-2 pr-4 font-medium">Job</th>
              <th className="py-2 font-medium">Step</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b">
                <td className="py-2 pr-4 tabular-nums">{r.at.slice(0, 10)}</td>
                <td className="py-2 pr-4">{r.company_name}</td>
                <td className="py-2 pr-4">{r.job_title ?? ''}</td>
                <td className="py-2">{STEP[r.step] ?? r.step}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Page>
  )
}
