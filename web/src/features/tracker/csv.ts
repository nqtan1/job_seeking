/** One CSV cell: quoted, and neutralised when a spreadsheet would read it as a formula. */
const cell = (v: string | null | undefined) => {
  const s = v ?? ''
  const safe = /^[=+\-@\t\r]/.test(s) ? `'${s}` : s
  return `"${safe.replaceAll('"', '""')}"`
}

export const toCsv = (rows: (string | null | undefined)[][]) =>
  rows.map((r) => r.map(cell).join(',')).join('\r\n')
