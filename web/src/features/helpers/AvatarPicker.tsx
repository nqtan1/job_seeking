import { useT } from '@/i18n'
import { Avatar } from './Avatar'
import { ACCESSORIES, type AvatarSpec, BODIES, EYES, PALETTES, PALETTES_COUNT } from './avatar'

const range = (n: number) => Array.from({ length: n }, (_, i) => i)

function Row({
  label,
  field,
  count,
  value,
  onChange,
}: {
  label: string
  field: 'body' | 'eyes' | 'accessory'
  count: number
  value: AvatarSpec
  onChange: (next: AvatarSpec) => void
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      <span className="w-14 shrink-0 text-xs font-medium text-muted-foreground">{label}</span>
      {range(count).map((i) => (
        <button
          key={i}
          type="button"
          aria-pressed={value[field] === i}
          aria-label={`${label} ${i + 1}`}
          onClick={() => onChange({ ...value, [field]: i })}
          className="grid size-8 place-items-center rounded-lg border bg-background outline-none transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:border-primary aria-pressed:bg-accent pointer-coarse:size-11"
        >
          <Avatar spec={{ ...value, [field]: i }} size={24} />
        </button>
      ))}
    </div>
  )
}

/** Choose each part of the character (the shuffle button lives next to the name). Parameters only. */
export function AvatarPicker({
  value,
  onChange,
}: {
  value: AvatarSpec
  onChange: (next: AvatarSpec) => void
}) {
  const t = useT()
  return (
    <div className="space-y-2.5">
      <Row
        value={value}
        onChange={onChange}
        label={t('helpers.avatar.body')}
        field="body"
        count={BODIES}
      />
      <Row
        value={value}
        onChange={onChange}
        label={t('helpers.avatar.eyes')}
        field="eyes"
        count={EYES}
      />
      <Row
        value={value}
        onChange={onChange}
        label={t('helpers.avatar.extra')}
        field="accessory"
        count={ACCESSORIES}
      />
      <div
        role="group"
        aria-label={t('helpers.avatar.color')}
        className="flex flex-wrap items-center gap-1"
      >
        <span className="w-14 shrink-0 text-xs font-medium text-muted-foreground">
          {t('helpers.avatar.color')}
        </span>
        {range(PALETTES_COUNT).map((i) => (
          <button
            key={i}
            type="button"
            aria-pressed={value.palette === i}
            aria-label={`${t('helpers.avatar.color')} ${i + 1}`}
            onClick={() => onChange({ ...value, palette: i })}
            style={{ background: PALETTES[i].fill, borderColor: PALETTES[i].accent }}
            className="size-5 rounded-full border-2 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:ring-2 aria-pressed:ring-foreground pointer-coarse:size-9"
          />
        ))}
      </div>
    </div>
  )
}
