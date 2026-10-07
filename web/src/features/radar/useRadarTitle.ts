import { useEffect } from 'react'
import { useRadarStatus } from './api'

/** "(3) RecruitAI" in the browser tab while there are new matches. */
export function useRadarTitle() {
  const count = useRadarStatus().data?.new_matches ?? 0
  useEffect(() => {
    document.title = count > 0 ? `(${count}) RecruitAI` : 'RecruitAI'
  }, [count])
}
