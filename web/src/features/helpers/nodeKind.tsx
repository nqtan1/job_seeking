// audit: keep-separate (kept out of Canvas so the lazy React Flow chunk stays apart from the Steps list)
import { Bot, Flag, type LucideIcon, Play, Split, Wand } from 'lucide-react'
import type { GraphNode } from './graph'

/** One icon and one accent class per step kind (colours live in index.css: `.kind-*`). */
export const KIND: Record<GraphNode['type'], { icon: LucideIcon; cls: string }> = {
  input: { icon: Play, cls: 'kind-input' },
  output: { icon: Flag, cls: 'kind-output' },
  condition: { icon: Split, cls: 'kind-condition' },
  transform: { icon: Wand, cls: 'kind-transform' },
  agent: { icon: Bot, cls: '' },
}
