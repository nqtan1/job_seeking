import { reminders } from '@/features/today/steps'

test('reminders: only what has a count, most urgent first', () => {
  expect(reminders({ failed: 0, followUps: 0, matches: 0 })).toEqual([])
  expect(
    reminders({ failed: 1, followUps: 0, matches: 4 }).map((r) => [r.key, r.to, r.count]),
  ).toEqual([
    ['failed', '/activity', 1],
    ['matches', '/radar', 4],
  ])
})
