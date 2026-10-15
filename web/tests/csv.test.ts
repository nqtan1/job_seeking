import { toCsv } from '@/features/tracker/csv'

test('quotes cells and neutralises spreadsheet formulas', () => {
  expect(toCsv([['a"b', '=SUM(A1)', null, 'ok']])).toBe(`"a""b","'=SUM(A1)","","ok"`)
})
