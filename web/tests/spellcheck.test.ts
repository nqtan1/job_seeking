import {
  activeIssues,
  applyAll,
  applyIssue,
  isStale,
  type SpellIssue,
} from '@/features/letters/spellcheck'

const issue = (text: string, wrong: string, right: string, nth = 0): SpellIssue => {
  let start = -1
  for (let n = 0; n <= nth; n++) start = text.indexOf(wrong, start + 1)
  return { key: 'body.0', start, end: start + wrong.length, wrong, right, reason: '' }
}

test('applying one correction re-aligns the others so they stay applicable in any order', () => {
  const text = 'Il à fini le developement du logiciel et il à gagné.'
  const issues = [
    issue(text, 'à', 'a'),
    issue(text, 'developement', 'développement'),
    issue(text, 'à', 'a', 1),
  ]
  // Apply the first one (shorter text), then the longer fix, then the last: all still land.
  let state = applyIssue(text, issues, 0)
  expect(state.text).toBe('Il a fini le developement du logiciel et il à gagné.')
  state = applyIssue(state.text, state.issues, 0) // 'developement' is now first
  expect(state.text).toContain('développement')
  state = applyIssue(state.text, state.issues, 0)
  expect(state.text).toBe('Il a fini le développement du logiciel et il a gagné.')
  expect(state.issues).toEqual([])
})

test('apply all gives the same text whatever order the issues come in', () => {
  const text = 'Mes collegues ont réduit le temp de déploiement.'
  const a = issue(text, 'collegues', 'collègues')
  const b = issue(text, 'temp', 'temps')
  expect(applyAll(text, [a, b])).toBe('Mes collègues ont réduit le temps de déploiement.')
  expect(applyAll(text, [b, a])).toBe('Mes collègues ont réduit le temps de déploiement.')
})

test('a result stops applying once the paragraph is edited', () => {
  const checked = { text: 'abc', issues: [] }
  expect(activeIssues(checked, 'abc')).toEqual([])
  expect(activeIssues(checked, 'abcd')).toBeUndefined()
  expect(activeIssues(undefined, 'abc')).toBeUndefined()
})

test('UTF-16 offsets from the API line up with JavaScript string indexes after an emoji', () => {
  const text = '🚀 Il à fini, il à gagné.'
  const start = text.lastIndexOf('à') // a JS (UTF-16) index, as the API now sends
  const issues = [{ key: 'body.0', start, end: start + 1, wrong: 'à', right: 'a', reason: '' }]
  expect(applyIssue(text, issues, 0).text).toBe('🚀 Il à fini, il a gagné.')
})

test('a span that no longer matches is dropped, never "fixed" somewhere else', () => {
  const text = 'Il à fini et il à gagné.'
  const stale = [{ key: 'body.0', start: 0, end: 1, wrong: 'à', right: 'a', reason: '' }]
  const out = applyIssue(text, stale, 0)
  expect(out.text).toBe(text) // untouched
  expect(out.issues).toEqual([])
})

test('isStale: only a checked paragraph that changed since', () => {
  expect(isStale(undefined, 'x')).toBe(false)
  expect(isStale({ text: 'x', issues: [] }, 'x')).toBe(false)
  expect(isStale({ text: 'x', issues: [] }, 'xy')).toBe(true)
})
