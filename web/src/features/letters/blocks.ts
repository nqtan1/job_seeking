import type { Key, Vars } from '@/i18n'
import type { Block, Letter } from './api'

type T = (key: Key, vars?: Vars) => string

type Ideas = NonNullable<Letter['ideas']>

export type EditorBlock = { key: string; block: Block; index?: number; label: string; text: string }

/** The editable blocks of a letter, in reading order (the body is one block per paragraph). */
export function editorBlocks(c: Letter['content'], t: T): EditorBlock[] {
  return [
    { key: 'subject', block: 'subject', label: t('letters.block.subject'), text: c.subject },
    {
      key: 'salutation',
      block: 'salutation',
      label: t('letters.block.salutation'),
      text: c.salutation,
    },
    { key: 'opening', block: 'opening', label: t('letters.block.opening'), text: c.opening },
    ...c.body.map((text, i) => ({
      key: `body.${i}`,
      block: 'body' as const,
      index: i,
      label: t('letters.block.paragraph', { n: i + 1 }),
      text,
    })),
    { key: 'closing', block: 'closing', label: t('letters.block.closing'), text: c.closing },
  ]
}

/** The writing ideas for one block, as short lines (empty when the letter has none, or none
 *  for this block, e.g. a paragraph that already holds the user's own words). */
export function ideasFor(ideas: Letter['ideas'], b: EditorBlock, t: T): string[] {
  if (!ideas) return []
  const i: Ideas = ideas
  if (b.block === 'opening') return i.opening
  if (b.block === 'closing') return i.closing
  if (b.block === 'body' && b.index !== undefined) {
    const idea = i.body[b.index]
    return idea
      ? [
          t('letters.idea.answer', { text: idea.requirement }),
          t('letters.idea.with', { text: idea.proof }),
          idea.angle,
        ]
      : []
  }
  return []
}
