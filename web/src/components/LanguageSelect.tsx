import { LANG_NAMES, LANGS, useI18n, type Lang } from '@/i18n'
import { NativeSelect } from '@/components/ui/native-select'

/** The one language switch. `onChange` saves it to the account when signed in; the interface
 *  switches immediately either way. */
export function LanguageSelect({
  onChange,
  id = 'language',
}: {
  onChange?: (lang: Lang) => void
  id?: string
}) {
  const { lang, t, setLang } = useI18n()
  return (
    <NativeSelect
      id={id}
      aria-label={t('lang.label')}
      value={lang}
      onChange={(e) => {
        const next = e.target.value as Lang
        setLang(next)
        onChange?.(next)
      }}
    >
      {LANGS.map((l) => (
        <option key={l} value={l}>
          {LANG_NAMES[l]}
        </option>
      ))}
    </NativeSelect>
  )
}
