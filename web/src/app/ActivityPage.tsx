import { Page } from '@/components/Page'
import { RunsTab } from '@/features/helpers/RunsPage'
import { useT } from '@/i18n'

/** Every run, promoted from the Flows page's history tab (which keeps working). */
export function ActivityPage() {
  return (
    <Page title={useT()('nav.activity')}>
      <RunsTab />
    </Page>
  )
}
