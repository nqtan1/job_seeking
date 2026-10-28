import { useSyncExternalStore } from 'react'
import { admin } from './messages/admin'
import { candidate } from './messages/candidate'
import { coach } from './messages/coach'
import { common } from './messages/common'
import { jobs } from './messages/jobs'
import { letters } from './messages/letters'
import { pipeline } from './messages/pipeline'
import { radar } from './messages/radar'
import { settings } from './messages/settings'
import { signature } from './messages/signature'
import { tracker } from './messages/tracker'

export const LANGS = ['en', 'fr', 'vi'] as const
export type Lang = (typeof LANGS)[number]
export const LANG_NAMES: Record<Lang, string> = { en: 'English', fr: 'Français', vi: 'Tiếng Việt' }
const LOCALES: Record<Lang, string> = { en: 'en-GB', fr: 'fr-FR', vi: 'vi-VN' }

/** One module per feature; a language file must define every key of its English file. */
const modules = [
  common,
  jobs,
  letters,
  tracker,
  candidate,
  pipeline,
  coach,
  radar,
  settings,
  admin,
  signature,
]
const en = Object.assign({}, ...modules.map((m) => m.en)) as UnionToObject
type UnionToObject = UnionToIntersection<(typeof modules)[number]['en']>
type UnionToIntersection<U> = (U extends unknown ? (x: U) => void : never) extends (
  x: infer I,
) => void
  ? I
  : never
const catalog: Record<Lang, Record<string, string>> = {
  en,
  fr: Object.assign({}, ...modules.map((m) => m.fr)),
  vi: Object.assign({}, ...modules.map((m) => m.vi)),
}

export type MessageKey = keyof UnionToObject
/** `foo_one` / `foo_other` are the plural forms of `foo`: call `t('foo', { count })`. */
type Base<K> = K extends `${infer B}_other` ? B : K
export type Key = MessageKey | Base<MessageKey>
export type Vars = Record<string, string | number>

const KEY = 'lang'

export function detectLang(): Lang {
  try {
    const stored = localStorage.getItem(KEY)
    if (LANGS.includes(stored as Lang)) return stored as Lang
  } catch {
    /* storage can be blocked: fall through to the browser's language */
  }
  for (const l of globalThis.navigator?.languages ?? []) {
    const short = l.slice(0, 2).toLowerCase()
    if (LANGS.includes(short as Lang)) return short as Lang
  }
  return 'en'
}

let current: Lang = detectLang()
const listeners = new Set<() => void>()

function apply(lang: Lang) {
  if (typeof document !== 'undefined') document.documentElement.lang = lang
}
apply(current)

/** Switch the interface now (and remember it on this device). Saving it to the account is the
 *  caller's job: see `useSetLanguage`. */
export function setLang(lang: Lang) {
  if (lang === current) return
  current = lang
  try {
    localStorage.setItem(KEY, lang)
  } catch {
    /* the choice then lasts for the session only */
  }
  apply(lang)
  listeners.forEach((l) => l())
}

const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => void listeners.delete(l)
}

export function translate(lang: Lang, key: Key, vars?: Vars): string {
  let k: string = key
  if (vars && typeof vars.count === 'number') {
    const form = `${key}_${new Intl.PluralRules(LOCALES[lang]).select(vars.count)}`
    if (form in catalog[lang]) k = form
    else if (`${key}_other` in catalog[lang]) k = `${key}_other`
  }
  const text = catalog[lang][k] ?? catalog.en[k] ?? k
  return vars ? text.replace(/\{(\w+)\}/g, (m, name: string) => String(vars[name] ?? m)) : text
}

export function useI18n() {
  const lang = useSyncExternalStore(subscribe, () => current)
  return {
    lang,
    locale: LOCALES[lang],
    setLang,
    t: (key: Key, vars?: Vars) => translate(lang, key, vars),
  }
}

export const useT = () => useI18n().t

/** For code outside React (toasts raised from a mutation callback). */
export const tNow = (key: Key, vars?: Vars) => translate(current, key, vars)

export const catalogs = catalog
export const currentLang = () => current
