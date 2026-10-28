import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { useI18n, type Key } from '@/i18n'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { AdminTabs } from './AdminTabs'
import { useAiConsole, useResetAiModel, useSetAiModel } from './api'

const COLS: (Key | '')[] = [
  'admin.ai.col.feature',
  'admin.ai.col.model',
  'admin.ai.col.prompt',
  'admin.ai.col.calls',
  'admin.ai.col.errors',
  'admin.ai.col.avg',
  'admin.ai.col.p95',
  'admin.ai.col.tokens',
  '',
]

/** What runs each AI feature and how it has behaved. Models only; prompts stay in code (ADR 0022). */
export function AdminAiPage() {
  const { t, locale } = useI18n()
  const num = (n: number) => n.toLocaleString(locale)
  const console_ = useAiConsole()
  const setModel = useSetAiModel()
  const reset = useResetAiModel()
  const choices = Object.entries(console_.data?.allowed_models ?? {}).flatMap(
    ([provider, models]) => models.map((model) => ({ provider, model })),
  )
  return (
    <Page title={t('admin.title')} description={t('admin.ai.description')} wide>
      <AdminTabs />
      {console_.isPending && <ListSkeleton rows={4} />}
      {console_.isError && <ErrorMessage error={console_.error} />}
      {(setModel.isError || reset.isError) && (
        <ErrorMessage error={setModel.error ?? reset.error} />
      )}
      {console_.data && (
        <>
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  {COLS.map((h, i) => (
                    <th key={i} className="p-3 font-medium">
                      {h && t(h)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {console_.data.features.map((f) => {
                  const value = `${f.provider}/${f.model}`
                  return (
                    <tr key={f.feature} className="border-t">
                      <td className="p-3 font-medium">{f.feature}</td>
                      <td className="p-3">
                        <NativeSelect
                          aria-label={t('admin.ai.model_for', { feature: f.feature })}
                          value={value}
                          disabled={setModel.isPending}
                          onChange={(e) => {
                            const [provider, ...rest] = e.target.value.split('/')
                            setModel.mutate({ feature: f.feature, provider, model: rest.join('/') })
                          }}
                        >
                          {!choices.some((c) => `${c.provider}/${c.model}` === value) && (
                            <NativeSelectOption value={value}>{value}</NativeSelectOption>
                          )}
                          {choices.map((c) => (
                            <NativeSelectOption
                              key={`${c.provider}/${c.model}`}
                              value={`${c.provider}/${c.model}`}
                            >
                              {c.provider}/{c.model}
                            </NativeSelectOption>
                          ))}
                        </NativeSelect>
                        {f.overridden && (
                          <p className="mt-1 text-xs text-warning">
                            {t('admin.ai.overridden', { default: f.default })}
                          </p>
                        )}
                      </td>
                      <td className="p-3">{f.prompt_version ?? '—'}</td>
                      <td className="p-3 tabular-nums">{num(f.calls)}</td>
                      <td className="p-3 tabular-nums">{num(f.errors)}</td>
                      <td className="p-3 tabular-nums">{num(f.avg_latency_ms)}</td>
                      <td className="p-3 tabular-nums">{num(f.p95_latency_ms)}</td>
                      <td className="p-3 tabular-nums">{num(f.input_tokens + f.output_tokens)}</td>
                      <td className="p-3 text-right">
                        {f.overridden && (
                          <Button
                            size="sm"
                            variant="outline"
                            aria-label={t('admin.ai.reset_aria', { feature: f.feature })}
                            disabled={reset.isPending}
                            onClick={() => reset.mutate(f.feature)}
                          >
                            {t('admin.ai.reset')}
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <section aria-label={t('admin.ai.changes')} className="space-y-1">
            <h2 className="text-sm font-semibold text-muted-foreground">{t('admin.ai.changes')}</h2>
            {console_.data.changes.length === 0 && (
              <p className="text-sm text-muted-foreground">{t('admin.ai.no_changes')}</p>
            )}
            <ul className="space-y-1 text-sm">
              {console_.data.changes.map((c) => (
                <li
                  key={`${c.feature}-${c.at}`}
                  className="flex flex-wrap justify-between gap-2 border-b py-1"
                >
                  <span>
                    {c.feature}: {c.old_value ?? t('admin.ai.default')} →{' '}
                    {c.new_value ?? t('admin.ai.default')}
                  </span>
                  <span className="text-muted-foreground">
                    {new Date(c.at).toLocaleString(locale)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </Page>
  )
}
