import type { Block, Letter } from './api'

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
