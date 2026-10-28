/** Save `text` as a file named `filename` (click a temporary link to a Blob URL). */
export function downloadBlob(filename: string, mime: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }))
  Object.assign(document.createElement('a'), { href: url, download: filename }).click()
  URL.revokeObjectURL(url)
}
