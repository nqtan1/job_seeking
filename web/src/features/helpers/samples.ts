import type { GraphNode, Specs, TOOL_IO } from './graph'

/** What a step gives back, as a user can picture it: each field with an example value. The
 *  examples are fixed illustrations (a finished run shows the real values). */
export type OutField = { name: string; example: string }

type ToolKind = keyof typeof TOOL_IO
// Typed from TOOL_IO: adding an output there fails to compile until it has an example here.
const TOOL_EXAMPLE: { [K in ToolKind]: Record<(typeof TOOL_IO)[K]['out'][number], string> } = {
  web_search: {
    text: 'Acme is hiring two data analysts in Lyon, hybrid, from 45k€.',
    sources: 'Acme careers: https://acme.example/careers',
  },
  job_search: {
    text: 'Data analyst · Acme · Lyon · https://acme.example/jobs/42\nBI developer · Beta · Paris · https://beta.example/jobs/7',
    count: '2',
  },
  find_offers: {
    items:
      '[{"job_id":"…","title":"Data analyst","company":"Acme","place":"Lyon","url":"https://acme.example/jobs/42"}, …]',
    text: 'Data analyst · Acme · Lyon · https://acme.example/jobs/42\n…',
    count: '2',
    remaining: '1',
  },
  fit_check: {
    score: '78',
    verdict: 'go',
    strengths: '- 3 years of Python and SQL\n- Dashboards for a similar team',
    gaps: '- No Airflow experience',
    missing: '- Airflow',
    reasons: '- Strong match on the core skills\n- One tool to learn',
  },
  for_each: { started: '3', text: 'the ids of the runs that were started' },
  read_page: {
    text: 'Acme is looking for a data analyst to join its team in Lyon… (the page text)',
  },
  job_lookup: {
    title: 'Data analyst',
    company: 'Acme',
    place: 'Lyon',
    description: 'You will build dashboards and… (the job description)',
    url: 'https://acme.example/jobs/42',
  },
  add_to_tracker: { status: 'added:…' },
  send_email: { status: 'sent' },
  telegram_send: { status: 'sent' },
  wait: { value: '(what the step received, passed on after the wait)' },
}

const BY_TYPE: Record<string, string> = {
  text: '…',
  number: '78',
  boolean: 'yes',
  list: '• …\n• …',
}

export function outputFields(node: GraphNode, specs: Specs): OutField[] {
  switch (node.type) {
    case 'input':
      return node.fields.map((f) => ({ name: f.name, example: `(${f.label})` }))
    case 'agent': {
      const out = specs.get(node.agent_version_id)?.output
      if (!out) return []
      if (out.kind === 'text') return [{ name: 'text', example: '(the helper’s answer, as text)' }]
      return (out.fields ?? []).map((f) => ({
        name: f.name,
        example: f.type === 'choice' ? (f.options?.[0] ?? '…') : (BY_TYPE[f.type] ?? '…'),
      }))
    }
    case 'condition':
      return [{ name: 'value', example: '(the text it received, unchanged)' }]
    case 'transform':
      return [{ name: 'text', example: '(the text, tidied)' }]
    case 'tool': {
      const ex: Record<string, string> = TOOL_EXAMPLE[node.tool]
      return Object.entries(ex).map(([name, example]) => ({ name, example }))
    }
    default:
      return []
  }
}
