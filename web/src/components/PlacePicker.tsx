import { ChevronDown, X } from 'lucide-react'
import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { filterRegions, placeLabel, placesLabel } from '@/lib/regions'
import { cn } from 'cn'

const split = (value: string | null | undefined) =>
  (value ?? '')
    .split(/[,\s;]+/)
    .map((c) => c.trim().toUpperCase())
    .filter(Boolean)

/**
 * Where to look, as a list: "All France" first, then Île-de-France (Paris first), then the other
 * regions with their departments and main cities. Tick several, or a whole region at once. The
 * value is the comma-separated department codes France Travail expects ("75,69"); null means all
 * of France.
 */
export function PlacePicker({
  value,
  onChange,
  label = 'Places',
}: {
  value: string | null | undefined
  onChange: (value: string | null) => void
  label?: string
}) {
  const codes = split(value)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const emit = (next: string[]) => onChange(next.length ? [...new Set(next)].join(',') : null)
  const toggle = (code: string) =>
    emit(codes.includes(code) ? codes.filter((c) => c !== code) : [...codes, code])
  const regions = filterRegions(query)

  return (
    <div role="group" aria-label={label} className="space-y-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full max-w-md items-center justify-between rounded-lg border bg-card px-3 py-2 text-left text-sm"
      >
        <span className="truncate">{placesLabel(value)}</span>
        <ChevronDown className={cn('size-4 shrink-0 transition-transform', open && 'rotate-180')} />
      </button>
      {codes.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {codes.map((c) => (
            <li
              key={c}
              className="flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs"
            >
              {placeLabel(c)}
              <button
                type="button"
                aria-label={`Remove ${placeLabel(c)}`}
                onClick={() => toggle(c)}
              >
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && (
        <div className="max-h-80 max-w-md space-y-3 overflow-y-auto rounded-lg border bg-popover p-3 shadow-md">
          <Input
            aria-label="Search places"
            placeholder="Search a city, department or region"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            type="button"
            aria-pressed={codes.length === 0}
            onClick={() => onChange(null)}
            className={cn(
              'w-full rounded-md border px-3 py-1.5 text-left text-sm font-medium',
              codes.length === 0 ? 'border-primary bg-primary text-primary-foreground' : 'bg-card',
            )}
          >
            All France
          </button>
          {regions.map((r) => {
            const all = r.departments.map((x) => x.code)
            const allOn = all.every((c) => codes.includes(c))
            return (
              <fieldset key={r.name} className="space-y-1">
                <legend className="flex w-full items-center justify-between text-xs font-semibold text-muted-foreground">
                  {r.name}
                  <button
                    type="button"
                    className="font-normal underline"
                    aria-label={`${allOn ? 'Clear' : 'Select all in'} ${r.name}`}
                    onClick={() =>
                      emit(allOn ? codes.filter((c) => !all.includes(c)) : [...codes, ...all])
                    }
                  >
                    {allOn ? 'Clear' : 'Select all'}
                  </button>
                </legend>
                {r.departments.map((x) => (
                  <label key={x.code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={codes.includes(x.code)}
                      onChange={() => toggle(x.code)}
                    />
                    {placeLabel(x.code)}
                  </label>
                ))}
              </fieldset>
            )
          })}
          {regions.length === 0 && (
            <p className="text-sm text-muted-foreground">Nothing matches “{query}”.</p>
          )}
        </div>
      )}
    </div>
  )
}
