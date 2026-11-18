// Fails the build when the JS a first visit downloads (the entry script + every modulepreload in
// index.html) is over budget: counting the entry alone is gamed by moving code into preloads.
// ponytail: 800 kB raw (~240 kB gzip, 2026-11-17); next lever is loading one language, not three.
// Usage: node scripts/bundle-budget.mjs [distDir]
import { readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const LIMIT_KB = 800
const dist = process.argv[2] ?? 'dist'
const html = readFileSync(join(dist, 'index.html'), 'utf8')
const files = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.js)"/g)].map((m) => m[1])
if (!files.length) {
  process.stderr.write('bundle-budget: no script in index.html\n')
  process.exit(1)
}
const kb = files.reduce((t, f) => t + statSync(join(dist, f)).size, 0) / 1000
process.stdout.write(
  `bundle-budget: first load ${kb.toFixed(1)} kB in ${files.length} files (limit ${LIMIT_KB} kB)\n`,
)
if (kb > LIMIT_KB) process.exit(1)
