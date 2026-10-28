import { describe, expect, it } from 'vitest'
import { catalogs, LANGS, translate } from '@/i18n'

const vars = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()

describe('i18n catalogs', () => {
  it('has the same keys and the same {placeholders} in every language', () => {
    for (const [key, text] of Object.entries(catalogs.en)) {
      for (const lang of LANGS) {
        const other = catalogs[lang][key]
        expect(other, `${lang} is missing ${key}`).toBeTruthy()
        expect(vars(other), `${lang}:${key} placeholders`).toEqual(vars(text))
      }
    }
  })

  it('has no long French or Vietnamese text left identical to the English one', () => {
    const same = Object.entries(catalogs.en).filter(
      ([k, t]) => t.length > 24 && (catalogs.fr[k] === t || catalogs.vi[k] === t),
    )
    expect(same.map(([k]) => k)).toEqual([])
  })

  it('fills variables and reads each language', () => {
    expect(translate('en', 'err.request_id', { id: 'abc' })).toBe('request id: abc')
    expect(translate('vi', 'lang.label')).toBe('Ngôn ngữ')
  })
})
