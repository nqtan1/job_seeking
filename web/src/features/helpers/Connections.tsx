import { useEffect } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { ConfirmButton } from '@/components/ConfirmButton'
import { useT } from '@/i18n'
import {
  useCheckTelegram,
  useConnections,
  useDisconnectTelegram,
  useStartTelegramLink,
} from './api'

const CHECK_EVERY_MS = 3000

/** The outside accounts the user's automations may use (ADR 0036). Telegram first. */
export function ConnectionsTab() {
  const list = useConnections()
  return (
    <div>
      {list.isPending ? (
        <ListSkeleton />
      ) : list.error ? (
        <ErrorMessage error={list.error} />
      ) : (
        <TelegramCard
          status={list.data.items.find((c) => c.provider === 'telegram')?.status}
          available={list.data.telegram_available}
        />
      )}
    </div>
  )
}

function TelegramCard({ status, available }: { status: string | undefined; available: boolean }) {
  const t = useT()
  const link = useStartTelegramLink()
  const check = useCheckTelegram()
  const disconnect = useDisconnectTelegram()
  const { mutate: look, isPending: looking } = check
  const waiting = status === 'pending'

  // While the person is in Telegram, look for their code every few seconds.
  useEffect(() => {
    if (!waiting) return
    const id = setInterval(() => {
      if (!looking) look()
    }, CHECK_EVERY_MS)
    return () => clearInterval(id)
  }, [waiting, looking, look])

  return (
    <section
      aria-labelledby="conn-telegram"
      className="space-y-3 rounded-2xl border bg-card p-4 text-card-foreground"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="conn-telegram" className="text-base font-semibold">
          Telegram
        </h2>
        {status === 'active' ? (
          <StatusBadge tone="success">{t('helpers.connections.connected')}</StatusBadge>
        ) : waiting ? (
          <StatusBadge tone="warning">{t('helpers.connections.waiting')}</StatusBadge>
        ) : (
          <StatusBadge>{t('helpers.connections.not_connected')}</StatusBadge>
        )}
      </div>
      <p className="text-sm text-muted-foreground">{t('helpers.connections.telegram_about')}</p>
      {!available ? (
        <p role="status" className="text-sm text-muted-foreground">
          {t('helpers.connections.unavailable')}
        </p>
      ) : status === 'active' ? (
        <ConfirmButton
          variant="outline"
          label={t('helpers.connections.disconnect')}
          confirmLabel={t('helpers.connections.disconnect_confirm')}
          cancelLabel={t('helpers.cancel')}
          pending={disconnect.isPending}
          onConfirm={(reset) => disconnect.mutate(undefined, { onSettled: reset })}
        />
      ) : (
        <div className="space-y-2">
          <Button
            disabled={link.isPending}
            onClick={() =>
              link.mutate(undefined, {
                // opened in the click's own turn of events, so pop-up blockers allow it
                onSuccess: (d) => window.open(d.url, '_blank', 'noopener,noreferrer'),
              })
            }
          >
            {link.isPending && <Spinner />}
            {waiting ? t('helpers.connections.open_again') : t('helpers.connections.connect')}
          </Button>
          {waiting && (
            <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
              <Spinner /> {t('helpers.connections.press_start')}
            </p>
          )}
        </div>
      )}
      <ErrorMessage error={link.error ?? check.error ?? disconnect.error} />
    </section>
  )
}
