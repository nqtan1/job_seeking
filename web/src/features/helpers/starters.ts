import type { Key, Vars } from '@/i18n'
import { type Graph, type VersionSpec, newId } from './graph'

const LANG = 'Always answer in the language of the notes you are given.'
const text: VersionSpec['output'] = { kind: 'text', fields: [] }

export type Starter = {
  id: string
  name: Key
  goal: Key
  /** Label of each declared input, in order, in the user's language. */
  inputLabels: Key[]
  spec: VersionSpec
}

/** Curated starting points: ordinary, editable helpers (no special powers, no sharing). */
export const STARTERS: Starter[] = [
  {
    id: 'followup',
    name: 'helpers.st.followup.name',
    goal: 'helpers.st.followup.goal',
    inputLabels: ['helpers.st.followup.input'],
    spec: {
      instructions: `Write a short, polite follow-up message (4 to 6 sentences) to a recruiter about an application. Use the notes for the company, the role and when I applied. Be warm, specific and never pushy. Do not invent facts. ${LANG}`,
      model_tier: 'fast',
      inputs: [{ name: 'notes', label: 'Company, role, when I applied', required: true }],
      context_sources: [],
      output: text,
    },
  },
  {
    id: 'redflags',
    name: 'helpers.st.redflags.name',
    goal: 'helpers.st.redflags.goal',
    inputLabels: [],
    spec: {
      instructions: `Read the job and list warning signs a job seeker should know about: vague duties, unrealistic requirements, pay or contract concerns, pressure wording. Then give a risk level. Only use what the job text says. ${LANG}`,
      model_tier: 'fast',
      inputs: [],
      context_sources: ['job'],
      output: {
        kind: 'fields',
        fields: [
          { name: 'risk', type: 'choice', options: ['low', 'medium', 'high'] },
          { name: 'signs', type: 'list', options: [] },
        ],
      },
    },
  },
  {
    id: 'interview',
    name: 'helpers.st.interview.name',
    goal: 'helpers.st.interview.goal',
    inputLabels: [],
    spec: {
      instructions: `Ask me one realistic interview question for this job, then give three bullet points on what a strong answer covers, using only facts from my profile. ${LANG}`,
      model_tier: 'smart',
      inputs: [],
      context_sources: ['job', 'profile'],
      output: text,
    },
  },
  {
    id: 'pitch',
    name: 'helpers.st.pitch.name',
    goal: 'helpers.st.pitch.goal',
    inputLabels: [],
    spec: {
      instructions: `Write a 30-second "why me" pitch for this job, in the first person, using only real strengths from my profile that match the job. No clichés. ${LANG}`,
      model_tier: 'fast',
      inputs: [],
      context_sources: ['job', 'profile'],
      output: text,
    },
  },
  {
    id: 'reply',
    name: 'helpers.st.reply.name',
    goal: 'helpers.st.reply.goal',
    inputLabels: ['helpers.st.reply.input'],
    spec: {
      instructions: `Draft a brief, professional reply to the recruiter message in the notes. Answer what they ask, propose next steps, keep it friendly. Do not promise anything that is not in the notes. ${LANG}`,
      model_tier: 'fast',
      inputs: [{ name: 'notes', label: 'The recruiter’s message', required: true }],
      context_sources: [],
      output: text,
    },
  },
]

export const BLANK_SPEC: VersionSpec = {
  instructions: 'Describe what this helper should do, in plain words.',
  model_tier: 'fast',
  inputs: [{ name: 'notes', label: 'Notes', required: true }],
  context_sources: [],
  output: text,
}

type Translate = (key: Key, vars?: Vars) => string

/** The spec with its input labels in the user's language (the instructions stay as written: they
 *  are what the model reads, and the user can edit them). A blank helper gets a hint in their
 *  language instead of the English placeholder. */
export function localized(spec: VersionSpec, labels: Key[], t: Translate): VersionSpec {
  const blank = spec === BLANK_SPEC
  return {
    ...spec,
    instructions: blank ? t('helpers.blank.instructions') : spec.instructions,
    inputs: (spec.inputs ?? []).map((i, k) => ({
      ...i,
      label: labels[k] ? t(labels[k]) : i.label,
    })),
  }
}

/** The server's cap on helpers per account (backend MAX_AGENTS_PER_ORG): a hint, the server decides. */

/** A ready-made automation: which starter helpers it needs and how they are wired. Step 0 is Start,
 *  1..n the helpers (in order), n+1 the Result. A link is [from, to, [input, value][]]. */
export type Template = {
  id: string
  name: Key
  hint: Key
  helpers: string[]
  start: { name: string; label: Key; required: boolean }[]
  result: { name: string; label: Key }[]
  links: [number, number, [string, string][]][]
}

const OPTIONAL_NOTES = { name: 'notes', label: 'helpers.pages.tpl.extra', required: false } as const

export const TEMPLATES: Template[] = [
  {
    id: 'followup',
    name: 'helpers.pages.tpl.followup.name',
    hint: 'helpers.pages.tpl.followup.hint',
    helpers: ['followup'],
    start: [{ name: 'notes', label: 'helpers.st.followup.input', required: true }],
    result: [{ name: 'message', label: 'helpers.pages.tpl.message' }],
    links: [
      [0, 1, [['notes', '{{notes}}']]],
      [1, 2, [['message', '{{text}}']]],
    ],
  },
  {
    id: 'redflags',
    name: 'helpers.pages.tpl.redflags.name',
    hint: 'helpers.pages.tpl.redflags.hint',
    helpers: ['redflags'],
    start: [OPTIONAL_NOTES],
    result: [
      { name: 'risk', label: 'helpers.pages.tpl.risk' },
      { name: 'signs', label: 'helpers.pages.tpl.signs' },
    ],
    links: [
      [0, 1, []],
      [
        1,
        2,
        [
          ['risk', '{{risk}}'],
          ['signs', '{{signs}}'],
        ],
      ],
    ],
  },
  {
    id: 'interview',
    name: 'helpers.pages.tpl.interview.name',
    hint: 'helpers.pages.tpl.interview.hint',
    helpers: ['interview', 'pitch'],
    start: [OPTIONAL_NOTES],
    result: [
      { name: 'question', label: 'helpers.pages.tpl.question' },
      { name: 'pitch', label: 'helpers.pages.tpl.pitch' },
    ],
    links: [
      [0, 1, []],
      [0, 2, []],
      [1, 3, [['question', '{{text}}']]],
      [2, 3, [['pitch', '{{text}}']]],
    ],
  },
]

/** The graph of a template, once its helpers exist: `steps` are those helpers, in order. */
export function templateGraph(
  tpl: Template,
  steps: { agent_id: string; agent_version_id: string }[],
  t: Translate,
): Graph {
  const ids = Array.from({ length: steps.length + 2 }, newId)
  const mid = ((steps.length - 1) * 130) / 2
  const last = steps.length + 1
  const field = (f: { name: string; label: Key; required?: boolean }) => ({
    name: f.name,
    label: t(f.label),
    required: f.required ?? true,
  })
  return {
    schema_version: 1,
    nodes: [
      { type: 'input', id: ids[0], position: { x: 0, y: mid }, fields: tpl.start.map(field) },
      ...steps.map((s, i) => ({
        type: 'agent' as const,
        id: ids[i + 1],
        position: { x: 340, y: i * 130 },
        ...s,
      })),
      {
        type: 'output',
        id: ids[last],
        position: { x: 680, y: mid },
        fields: tpl.result.map(field),
      },
    ],
    edges: tpl.links.map(([from, to, map]) => ({
      id: newId(),
      from: { node: ids[from], port: 'out' },
      to: ids[to],
      map: map.map(([input, value]) => ({ input, value })),
    })),
  }
}
