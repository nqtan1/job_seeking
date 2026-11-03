import type { components } from '@/lib/api/schema'

export type AvatarSpec = components['schemas']['Avatar']

export const BODIES = 8
export const PALETTES_COUNT = 12
export const EYES = 6
export const ACCESSORIES = 8

/** Fill, accent, ink. Each pair keeps ≥ 4.5:1 between ink and fill (face on body) in both themes. */
export const PALETTES: { fill: string; accent: string; ink: string }[] = [
  { fill: '#fbd38d', accent: '#c05621', ink: '#3b2410' },
  { fill: '#9ae6b4', accent: '#2f855a', ink: '#12301f' },
  { fill: '#90cdf4', accent: '#2b6cb0', ink: '#102a4c' },
  { fill: '#fbb6ce', accent: '#b83280', ink: '#4a1530' },
  { fill: '#d6bcfa', accent: '#6b46c1', ink: '#2b1a52' },
  { fill: '#faf089', accent: '#975a16', ink: '#3d2a06' },
  { fill: '#feb2b2', accent: '#c53030', ink: '#4a1414' },
  { fill: '#81e6d9', accent: '#2c7a7b', ink: '#0f3234' },
  { fill: '#cbd5e0', accent: '#4a5568', ink: '#1a202c' },
  { fill: '#fbd5a5', accent: '#9c4221', ink: '#3b1d0e' },
  { fill: '#c3dafe', accent: '#4c51bf', ink: '#1e2352' },
  { fill: '#c6f6d5', accent: '#276749', ink: '#10301f' },
]

const clamp = (n: number, max: number) => Math.min(Math.max(Math.trunc(n) || 0, 0), max - 1)

/** A stable character for any string (template cards): FNV-1a, then the same part picking. */
export function avatarFromSeed(text: string): AvatarSpec {
  let h = 0x811c9dc5
  for (const ch of text) h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0
  const next = () => ((h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d) >>> 0), h)
  return {
    seed: `00000000-0000-7000-8000-${(h >>> 0).toString(16).padStart(12, '0')}`,
    body: next() % BODIES,
    palette: next() % PALETTES_COUNT,
    eyes: next() % EYES,
    accessory: next() % ACCESSORIES,
  }
}

export function shuffled(): AvatarSpec {
  const r = new Uint8Array(4)
  crypto.getRandomValues(r)
  return {
    seed: crypto.randomUUID(),
    body: r[0] % BODIES,
    palette: r[1] % PALETTES_COUNT,
    eyes: r[2] % EYES,
    accessory: r[3] % ACCESSORIES,
  }
}

/** A spec that is always drawable, whatever the server sent. */
export function safe(a: AvatarSpec): AvatarSpec {
  return {
    ...a,
    body: clamp(a.body, BODIES),
    palette: clamp(a.palette, PALETTES_COUNT),
    eyes: clamp(a.eyes, EYES),
    accessory: clamp(a.accessory, ACCESSORIES),
  }
}

export type Mood = 'idle' | 'queued' | 'thinking' | 'done' | 'failed' | 'skipped'

/** What the avatar shows for a step's server status. */
export function moodOf(status: string | undefined): Mood {
  switch (status) {
    case 'running':
      return 'thinking'
    case 'done':
      return 'done'
    case 'failed':
      return 'failed'
    case 'skipped':
      return 'skipped'
    case 'pending':
      return 'queued'
    default:
      return 'idle'
  }
}
