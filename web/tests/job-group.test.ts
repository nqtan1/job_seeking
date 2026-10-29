import { companyKey, dayBucket, inRange, stageOf } from '@/features/job-search/group'

const now = new Date(2026, 9, 29, 15, 0)
const at = (daysBack: number, h = 9) => new Date(2026, 9, 29 - daysBack, h).toISOString()

test('companyKey merges legal suffixes but never inner words; unknown stays null', () => {
  const k = companyKey('Thales')
  expect(companyKey('THALES SA')).toBe(k)
  expect(companyKey('Thales Group')).toBe(k)
  expect(companyKey('Thales S.A.')).toBe(k)
  expect(companyKey('Thales Alenia Space')).not.toBe(k)
  expect(companyKey('Dassault Systèmes')).toBe(companyKey('dassault systemes SA'))
  expect(companyKey('Entreprise non divulguée')).toBeNull()
  expect(companyKey('  ')).toBeNull()
  expect(companyKey('Group')).toBe('group')
})

test('date presets use local calendar days', () => {
  expect(inRange(at(0, 0), 'today', now)).toBe(true)
  expect(inRange(at(1, 23), 'today', now)).toBe(false)
  expect(inRange(at(6), '7', now)).toBe(true)
  expect(inRange(at(7), '7', now)).toBe(false)
  expect(inRange(at(29), '30', now)).toBe(true)
  expect(inRange(at(99), 'all', now)).toBe(true)
  expect(dayBucket(at(1), now)).toBe('yesterday')
  expect(dayBucket(at(40), now)).toBe('earlier')
  expect(stageOf(true, false, 'in_review')).toBe(3)
  expect(stageOf(true, true, 'to_apply')).toBe(2)
})
