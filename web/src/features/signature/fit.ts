/** Printed-size rules; mirror of backend `signature_spec.py` (the renderer enforces the same). */
export interface SigLimits {
  min_width_mm: number
  max_width_mm: number
  max_height_mm: number
  min_dpi: number
}
export type FitAlert = 'too_small' | 'too_big' | 'low_resolution'

const MIN_READABLE_W = 25
const MIN_READABLE_H = 8

export function fit(widthMm: number, aspect: number, widthPx: number, l: SigLimits) {
  const heightMm = widthMm / aspect
  const alerts: FitAlert[] = []
  if (widthMm < MIN_READABLE_W || heightMm < MIN_READABLE_H) alerts.push('too_small')
  if (widthMm > l.max_width_mm || heightMm > l.max_height_mm) alerts.push('too_big')
  // The renderer clamps the width, then shrinks it until the height fits.
  const clamped = Math.min(Math.max(widthMm, l.min_width_mm), l.max_width_mm)
  const printedWidthMm = Math.min(clamped, l.max_height_mm * aspect)
  if (widthPx / (printedWidthMm / 25.4) < l.min_dpi) alerts.push('low_resolution')
  return {
    alerts,
    heightMm,
    printedWidthMm,
    printedHeightMm: printedWidthMm / aspect,
    shrunk: printedWidthMm < widthMm - 0.5,
  }
}
