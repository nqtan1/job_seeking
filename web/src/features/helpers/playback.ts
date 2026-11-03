import { type Mood, moodOf } from './avatar'
import { useEffect, useRef, useState } from 'react'
import { type Key, catalogs, useT } from '@/i18n'

type StepLike = { node_id: string; position: number; status: string }

type Beat = { node: string; mood: Mood }

/** Total time budget for catching up after a poll brings several changes at once. */
export const CATCH_UP_MS = 1500
const BEAT_MS = 400

/**
 * What changed between two polls, as an ordered list of avatar moods to play. The animation is
 * driven by the server state, never by its own clock; when several things changed at once they
 * play in execution order and are compressed to fit the budget, and the last beat of each node is
 * always its real mood, so the screen can never end up lying.
 */
export function beatsBetween(prev: StepLike[], next: StepLike[]): Beat[] {
  const before = new Map(prev.map((s) => [s.node_id, s.status]))
  return [...next]
    .sort((a, b) => a.position - b.position)
    .filter((s) => before.get(s.node_id) !== s.status)
    .map((s) => ({ node: s.node_id, mood: moodOf(s.status) }))
}

/** Delay between beats so the whole catch-up fits the budget (never longer than a normal beat). */
export const spacing = (beats: number, budget = CATCH_UP_MS): number =>
  beats <= 1 ? 0 : Math.min(BEAT_MS, Math.floor(budget / beats))

/** The mood each node is shown with after applying `shown` beats on top of the previous state. */
export function moodsAfter(prev: StepLike[], beats: Beat[], shown: number): Map<string, Mood> {
  const moods = new Map(prev.map((s) => [s.node_id, moodOf(s.status)]))
  for (const b of beats.slice(0, shown)) moods.set(b.node, b.mood)
  return moods
}

/** Replay of a finished run: one frame per step in execution order; frame k has the first k+1 done. */
export function replayFrames(steps: StepLike[]): Map<string, Mood>[] {
  const ordered = [...steps].sort((a, b) => a.position - b.position)
  return ordered.map((_, k) => {
    const m = new Map<string, Mood>()
    ordered.forEach((s, i) => {
      if (i < k) m.set(s.node_id, moodOf(s.status))
      else if (i === k) m.set(s.node_id, moodOf(s.status))
      else m.set(s.node_id, 'queued')
    })
    return m
  })
}

type Hand = { edge_id: string; to_node: string }

/**
 * The moods to show for a live run, and the edges a packet should travel now. State comes only
 * from the server's steps; a poll that brings several changes plays them in order within a short
 * budget, and the end state is always the real one. Hidden tabs and reduced motion skip playing.
 */
export function usePlayback(
  steps: (StepLike & { node_id: string })[] | undefined,
  handoffs: Hand[],
) {
  const prev = useRef<StepLike[] | null>(null)
  const [moods, setMoods] = useState<Map<string, Mood>>(new Map())
  const [packets, setPackets] = useState<Map<string, number>>(new Map())
  const timers = useRef<number[]>([])
  const counter = useRef(0)

  useEffect(() => {
    if (!steps) {
      prev.current = null // another run (or none) starts from its real state, not from this one's
      return
    }
    const truth = new Map(steps.map((s) => [s.node_id, moodOf(s.status)]))
    const before = prev.current
    prev.current = steps
    timers.current.forEach(clearTimeout)
    timers.current = []
    const calm =
      document.hidden || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
    if (!before || calm) {
      setMoods(truth)
      return
    }
    const beats = beatsBetween(before, steps)
    if (beats.length === 0) {
      setMoods(truth)
      return
    }
    const gap = Math.max(spacing(beats.length), 60)
    setMoods(moodsAfter(before, beats, 0))
    beats.forEach((b, i) => {
      timers.current.push(
        window.setTimeout(() => {
          setMoods(moodsAfter(before, beats, i + 1))
          // a step starting or finishing receives its inputs: the packets arriving at it travel
          if (b.mood === 'thinking' || b.mood === 'skipped') return
          const into = handoffs.filter((h) => h.to_node === b.node)
          if (into.length)
            setPackets((p) => {
              const next = new Map(p)
              for (const h of into) next.set(h.edge_id, ++counter.current)
              return next
            })
        }, i * gap),
      )
    })
    timers.current.push(window.setTimeout(() => setMoods(truth), beats.length * gap + BEAT_MS))
    return () => timers.current.forEach(clearTimeout)
    // handoffs only add packets for beats of this poll; they are read through the closure
  }, [steps, handoffs])

  return { moods, packets }
}

/** A run error code in plain words (falls back to the generic message). */
export function useErrText() {
  const t = useT()
  return (code: string | null | undefined) => {
    const key = `helpers.rerr.${code}`
    return t((key in catalogs.en ? key : 'helpers.rerr.generic') as Key)
  }
}
