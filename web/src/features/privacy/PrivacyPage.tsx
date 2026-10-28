import { Link } from 'react-router'
import { useT, type Key } from '@/i18n'

const ROWS: [Key, Key][] = [
  ['privacy.r1', 'privacy.d1'],
  ['privacy.r2', 'privacy.d2'],
  ['privacy.r3', 'privacy.d3'],
  ['privacy.r4', 'privacy.d4'],
  ['privacy.r5', 'privacy.d5'],
  ['privacy.r6', 'privacy.d6'],
  ['privacy.r7', 'privacy.d7'],
  ['privacy.r8', 'privacy.d8'],
  ['privacy.r9', 'privacy.d9'],
]

export function PrivacyPage() {
  const t = useT()
  return (
    <main className="mx-auto max-w-2xl space-y-6 px-4 py-10">
      <h1 className="text-2xl font-semibold">{t('privacy.title')}</h1>
      <p className="text-sm text-muted-foreground">{t('privacy.intro')}</p>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">{t('privacy.h_process')}</h2>
        <p>{t('privacy.process')}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">{t('privacy.h_where')}</h2>
        <p>
          {t('privacy.where_a')} <strong>{t('privacy.where_b')}</strong>
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">{t('privacy.h_keep')}</h2>
        <ul className="divide-y rounded-lg border">
          {ROWS.map(([what, howLong]) => (
            <li key={what} className="grid gap-1 p-3 sm:grid-cols-2">
              <span>{t(what)}</span>
              <span className="text-muted-foreground">{t(howLong)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">{t('privacy.h_rights')}</h2>
        <p>{t('privacy.rights')}</p>
      </section>

      <Link to="/signin" className="text-sm text-primary underline">
        {t('privacy.back')}
      </Link>
    </main>
  )
}
