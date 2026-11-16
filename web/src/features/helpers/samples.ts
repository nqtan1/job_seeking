import { type GraphNode, type Specs, outputsOf } from './graph'

/** What a step gives back, as a user can picture it: each field with an example value. The
 *  examples are fixed illustrations (a finished run shows the real values). */
export type OutField = { name: string; example: string }

/** Examples by output name, whatever tool gives it: a tool a pack adds shows "…" for new names. */
const EXAMPLE: Record<string, string> = {
  text: 'Data analyst · Acme · Lyon · https://acme.example/jobs/42\n…',
  sources: 'Acme careers: https://acme.example/careers',
  count: '2',
  items: '[{"job_id":"…","title":"Data analyst","company":"Acme","place":"Lyon"}, …]',
  remaining: '1',
  score: '78',
  verdict: 'go',
  strengths: '- 3 years of Python and SQL\n- Dashboards for a similar team',
  gaps: '- No Airflow experience',
  missing: '- Airflow',
  reasons: '- Strong match on the core skills\n- One tool to learn',
  started: '3',
  title: 'Data analyst',
  company: 'Acme',
  place: 'Lyon',
  description: 'You will build dashboards and… (the job description)',
  url: 'https://acme.example/jobs/42',
  status: 'sent',
  value: '(what the step received, passed on)',
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
    case 'tool':
      return outputsOf(node, specs).map((name) => ({ name, example: EXAMPLE[name] ?? '…' }))
    default:
      return []
  }
}
