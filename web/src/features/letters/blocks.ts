import type { Block, Letter } from './api'

type Ideas = NonNullable<Letter['ideas']>

export type EditorBlock = { key: string; block: Block; index?: number; label: string; text: string }

/** The editable blocks of a letter, in reading order (the body is one block per paragraph). */
export function editorBlocks(c: Letter['content']): EditorBlock[] {
  return [
    { key: 'subject', block: 'subject', label: 'Subject', text: c.subject },
    { key: 'salutation', block: 'salutation', label: 'Salutation', text: c.salutation },
    { key: 'opening', block: 'opening', label: 'Opening', text: c.opening },
    ...c.body.map((text, i) => ({
      key: `body.${i}`,
      block: 'body' as const,
      index: i,
      label: `Paragraph ${i + 1}`,
      text,
    })),
    { key: 'closing', block: 'closing', label: 'Closing', text: c.closing },
  ]
}

/** The writing ideas for one block, as short lines (empty when the letter has none, or none
 *  for this block, e.g. a paragraph that already holds the user's own words). */
export function ideasFor(ideas: Letter['ideas'], b: EditorBlock): string[] {
  if (!ideas) return []
  const i: Ideas = ideas
  if (b.block === 'opening') return i.opening
  if (b.block === 'closing') return i.closing
  if (b.block === 'body' && b.index !== undefined) {
    const idea = i.body[b.index]
    return idea ? [`Answer: ${idea.requirement}`, `With: ${idea.proof}`, idea.angle] : []
  }
  return []
}
