/** The English file is the source: a French or Vietnamese file that misses a key, or has an
 *  extra one, does not compile. */
export function defineMessages<const T extends Record<string, string>>(m: {
  en: T
  fr: Record<keyof T, string>
  vi: Record<keyof T, string>
}) {
  return m
}
