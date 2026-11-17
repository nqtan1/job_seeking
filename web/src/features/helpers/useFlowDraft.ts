import { useEffect, useRef, useState } from 'react'
import { useT } from '@/i18n'
import { toast } from '@/lib/toast'
import { type FlowDetail, isConflict, useAddFlowVersion, useFetchFlow, useValidate } from './api'
import { clearDraft, loadDraft, saveDraft } from './lib'
import type { Graph, Issue } from './graph'

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

/** The graph being edited: kept as a local draft until saved as a new version, checked by the
 *  server after each pause. */
export function useFlowDraft(detail: FlowDetail) {
  const t = useT()
  const key = `flow-draft:${detail.id}`
  const [graph, setGraph] = useState<Graph>(() => {
    const kept = loadDraft<{ base: number; graph: Graph }>(key)
    return kept && kept.base === detail.current_version && !same(kept.graph, detail.graph)
      ? kept.graph
      : detail.graph
  })
  const [base, setBase] = useState(detail.current_version)
  const [saved, setSaved] = useState<Graph>(detail.graph)
  const [issues, setIssues] = useState<Issue[] | undefined>(detail.issues)
  const [conflict, setConflict] = useState(false)
  const add = useAddFlowVersion()
  const { mutate: checkGraph } = useValidate()
  const fetchFlow = useFetchFlow()

  const dirty = !same(graph, saved)
  useEffect(() => {
    if (dirty) saveDraft(key, { base, graph })
    else clearDraft(key)
  }, [dirty, graph, base, key])
  const leaving = useRef(false) // raised just before a deliberate reload

  // The server is the only judge: ask after a pause, keep only the newest answer.
  const ask = useRef(0)
  useEffect(() => {
    const mine = ++ask.current
    const id = setTimeout(() => {
      checkGraph(graph, {
        onSuccess: (r) => {
          if (mine === ask.current) setIssues(r.issues)
        },
      })
    }, 500)
    return () => clearTimeout(id)
    // `validate` is a stable mutation object; the graph is the input
  }, [graph, checkGraph])

  const save = async () => {
    setConflict(false)
    try {
      const v = await add.mutateAsync({ id: detail.id, basedOn: base, graph })
      setBase(v.version)
      setSaved(graph)
      clearDraft(key)
      toast(t('helpers.saved'))
    } catch (e) {
      if (isConflict(e)) setConflict(true)
    }
  }
  const reload = () => {
    clearDraft(key)
    leaving.current = true // a deliberate reload must not ask again
    window.location.reload()
  }
  const keepMine = async () => {
    // build on what the server has now, so the next save is not refused again
    const fresh = await fetchFlow(detail.id)
    setBase(fresh.current_version)
    setConflict(false)
  }
  return {
    graph,
    setGraph,
    base,
    saved,
    dirty,
    issues,
    conflict,
    add,
    leaving,
    save,
    reload,
    keepMine,
  }
}
