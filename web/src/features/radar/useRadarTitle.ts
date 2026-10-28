import { useEffect } from 'react'
import { tNow, useI18n } from '@/i18n'
import { useRadarStatus } from './api'

/** "(3) RecruitAI" in the browser tab while there are new matches. */
export function useRadarTitle() {
  const { lang } = useI18n()
  const count = useRadarStatus().data?.new_matches ?? 0
  useEffect(() => {
    document.title = count > 0 ? tNow('radar.tab_title', { count }) : 'RecruitAI'
  }, [count, lang])
}
