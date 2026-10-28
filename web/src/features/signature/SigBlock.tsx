import { useT } from '@/i18n'
import type { Signature } from './api'

const PX_PER_MM = 3

/** The signature on a checkerboard, above the printed name, drawn to scale. */
export function SigBlock({
  sig,
  widthMm,
  name,
}: {
  sig: Signature
  widthMm: number
  name?: string | null
}) {
  const t = useT()
  return (
    <div className="inline-block max-w-full rounded-md border bg-white p-4 text-black">
      <div
        className="[background:repeating-conic-gradient(#e5e5e5_0%_25%,#fff_0%_50%)_50%/12px_12px]"
        style={{ width: widthMm * PX_PER_MM, maxWidth: '100%' }}
      >
        <img
          src={sig.url}
          alt={t('signature.alt')}
          className="block h-auto w-full"
          width={sig.width_px}
          height={sig.height_px}
        />
      </div>
      <p className="mt-1 text-sm">{name || '…'}</p>
    </div>
  )
}
