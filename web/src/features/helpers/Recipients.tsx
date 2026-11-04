import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorMessage } from '@/components/ErrorMessage'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useT } from '@/i18n'
import { useAddContact, useContacts, useRemoveContact } from './api'

/** Who the user's automations may email: themselves, plus people who confirmed. */
export function ContactsTab() {
  const t = useT()
  const contacts = useContacts()
  const remove = useRemoveContact()
  return (
    <div className="space-y-4 pt-6">
      <p className="rounded-2xl bg-muted/40 p-4 text-sm text-muted-foreground">
        {t('helpers.contacts.intro')}
      </p>
      <AddContact />
      <ErrorMessage error={remove.error} />
      {contacts.isPending ? (
        <ListSkeleton />
      ) : contacts.error ? (
        <ErrorMessage error={contacts.error} />
      ) : (
        <ul className="divide-y rounded-2xl border">
          {contacts.data.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <span className="min-w-0 break-all text-sm font-medium">{c.email}</span>
              <span className="flex items-center gap-2">
                <StatusBadge tone={c.status === 'confirmed' ? 'success' : 'warning'}>
                  {c.status === 'confirmed'
                    ? t('helpers.contacts.confirmed')
                    : t('helpers.contacts.pending')}
                </StatusBadge>
                <ConfirmButton
                  variant="ghost"
                  label={
                    <>
                      <Trash2 aria-hidden /> {t('helpers.contacts.remove')}
                    </>
                  }
                  aria-label={t('helpers.contacts.remove_for', { email: c.email })}
                  confirmLabel={t('helpers.contacts.remove_confirm')}
                  confirmAriaLabel={t('helpers.contacts.remove_confirm_for', { email: c.email })}
                  cancelLabel={t('helpers.cancel')}
                  pending={remove.isPending}
                  onConfirm={(reset) => remove.mutate(c.id, { onSettled: reset })}
                />
              </span>
            </li>
          ))}
          {contacts.data.length === 0 && (
            <li className="p-4 text-sm text-muted-foreground">{t('helpers.contacts.empty')}</li>
          )}
        </ul>
      )}
    </div>
  )
}

function AddContact() {
  const t = useT()
  const add = useAddContact()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState('')
  const value = email.trim()
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (!value || add.isPending) return
        setSent('')
        add.mutate(value, {
          onSuccess: () => {
            setSent(value)
            setEmail('')
          },
        })
      }}
    >
      <Label htmlFor="contact-email">{t('helpers.contacts.add')}</Label>
      <div className="flex flex-wrap gap-2">
        <Input
          id="contact-email"
          type="email"
          autoComplete="off"
          className="min-w-0 flex-1 basis-56"
          placeholder={t('helpers.contacts.placeholder')}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Button type="submit" disabled={!value || add.isPending}>
          {add.isPending && <Spinner />}
          {t('helpers.contacts.add_button')}
        </Button>
      </div>
      <ErrorMessage error={add.error} />
      {sent && (
        <p role="status" className="text-sm text-muted-foreground">
          {t('helpers.contacts.sent', { email: sent })}
        </p>
      )}
    </form>
  )
}
