import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { cn } from 'cn'

/** France Travail contract codes the user can tick. Anything else goes in "Other". */
const KNOWN: [code: string, label: string][] = [
  ['CDI', 'CDI'],
  ['CDD', 'CDD'],
  ['MIS', 'Intérim'],
  ['SAI', 'Seasonal'],
  ['LIB', 'Freelance'],
  ['FRA', 'Franchise'],
]
const KNOWN_CODES = KNOWN.map(([code]) => code)

const split = (value: string | null | undefined) =>
  (value ?? '')
    .split(/[,\s;]+/)
    .map((c) => c.trim().toUpperCase())
    .filter(Boolean)

/**
 * Contract types as a list: tick several, "All contracts" for none, or type other codes
 * (e.g. CCE, REP). The value is the comma-separated codes France Travail expects ("CDI,CDD");
 * null means all contracts.
 */
export function ContractPicker({
  value,
  onChange,
  label = 'Contract types',
}: {
  value: string | null | undefined
  onChange: (value: string | null) => void
  label?: string
}) {
  const codes = split(value)
  const ticked = codes.filter((c) => KNOWN_CODES.includes(c))
  const [other, setOther] = useState(codes.filter((c) => !KNOWN_CODES.includes(c)).join(', '))

  const emit = (known: string[], extra: string) => {
    const all = [...new Set([...known, ...split(extra)])]
    onChange(all.length ? all.join(',') : null)
  }
  const toggle = (code: string) =>
    emit(ticked.includes(code) ? ticked.filter((c) => c !== code) : [...ticked, code], other)

  const chip = (on: boolean) =>
    cn(
      'rounded-full border px-3 py-1 text-xs transition-colors',
      on ? 'border-primary bg-primary text-primary-foreground' : 'bg-card hover:bg-accent',
    )
  return (
    <div role="group" aria-label={label} className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          aria-pressed={codes.length === 0}
          className={chip(codes.length === 0)}
          onClick={() => {
            setOther('')
            onChange(null)
          }}
        >
          All contracts
        </button>
        {KNOWN.map(([code, text]) => (
          <button
            key={code}
            type="button"
            aria-pressed={ticked.includes(code)}
            className={chip(ticked.includes(code))}
            onClick={() => toggle(code)}
          >
            {text}
          </button>
        ))}
      </div>
      <Input
        aria-label="Other contract codes"
        placeholder="Other codes, e.g. CCE, REP"
        value={other}
        onChange={(e) => {
          setOther(e.target.value)
          emit(ticked, e.target.value)
        }}
        className="max-w-xs"
      />
    </div>
  )
}
