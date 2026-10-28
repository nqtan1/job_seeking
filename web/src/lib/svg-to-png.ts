const MAX_SIDE = 1600
const FALLBACK = 600

/**
 * SVG file -> transparent PNG. The SVG is only loaded through an `<img>` (no script or external
 * reference ever runs) and is never uploaded: only the PNG is.
 */
export async function svgToPng(file: File): Promise<Blob> {
  const url = URL.createObjectURL(file)
  try {
    const img = new Image()
    await new Promise<void>((ok, fail) => {
      img.onload = () => ok()
      img.onerror = () => fail(new Error('svg'))
      img.src = url
    })
    // naturalWidth honours width/height or the viewBox; browsers report 0 when it has neither.
    const w = img.naturalWidth || FALLBACK
    const h = img.naturalHeight || Math.round(FALLBACK / 2)
    const k = MAX_SIDE / Math.max(w, h)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(w * k))
    canvas.height = Math.max(1, Math.round(h * k))
    canvas.getContext('2d')?.drawImage(img, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, 'image/png'))
    if (!blob) throw new Error('png')
    return blob
  } finally {
    URL.revokeObjectURL(url)
  }
}
