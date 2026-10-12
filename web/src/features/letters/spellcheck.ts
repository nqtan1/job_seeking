import type { components } from '@/lib/api/schema'

export type SpellIssue = components['schemas']['SpellIssue']

/** The result of one check, tied to the exact text that was checked. `ignored` counts the
 *  corrections the user dismissed, so "nothing left" is not mistaken for "nothing found". */
export type Checked = { text: string; issues: SpellIssue[]; ignored?: number }

/** The issues still valid for `current`, or `undefined` if the paragraph was not checked or
 *  has been edited since (the offsets would be wrong, so the user must check again). */
export function activeIssues(checked: Checked | undefined, current: string) {
  return checked && checked.text === current ? checked.issues : undefined
}

/** Checked once, then edited: the result is kept out of sight but the user is told. */
export function isStale(checked: Checked | undefined, current: string) {
  return checked !== undefined && checked.text !== current
}

/** Apply issue number `at`. Offsets are UTF-16 code units, exactly what `slice` uses, and the
 *  text is the one that was checked. If the span no longer matches (it should not happen) the
 *  issue is dropped: guessing a place could change a correct word. The remaining issues come
 *  back re-aligned, so they stay applicable one by one in any order. */
export function applyIssue(text: string, issues: SpellIssue[], at: number) {
  const issue = issues[at]
  const rest = issues.filter((_, i) => i !== at)
  if (text.slice(issue.start, issue.end) !== issue.wrong) return { text, issues: rest }
  const delta = issue.right.length - issue.wrong.length
  return {
    text: text.slice(0, issue.start) + issue.right + text.slice(issue.end),
    issues: rest.map((r) =>
      r.start >= issue.end ? { ...r, start: r.start + delta, end: r.end + delta } : r,
    ),
  }
}

/** Apply every issue, last first, so earlier offsets stay valid. */
export function applyAll(text: string, issues: SpellIssue[]) {
  let state = { text, issues }
  while (state.issues.length > 0) {
    const last = state.issues.reduce((m, r, i) => (r.start > state.issues[m].start ? i : m), 0)
    state = applyIssue(state.text, state.issues, last)
  }
  return state.text
}
