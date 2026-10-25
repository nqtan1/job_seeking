import { useForm } from 'react-hook-form'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useEditRecipient, type Letter } from './api'

/** Company, contact and address printed on the letter; empty ones are the model's misses. */
export function RecipientPanel({ letter }: { letter: Letter }) {
  const r = letter.content.recipient
  const edit = useEditRecipient(letter.id)
  const { register, handleSubmit } = useForm({
    defaultValues: {
      company: r.company ?? '',
      contact_name: r.contact_name ?? '',
      address: r.address ?? '',
    },
  })
  const empty = !r.company?.trim() && !r.contact_name?.trim() && !r.address?.trim()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recipient</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleSubmit((v) => edit.mutate(v))}>
          {empty && (
            <p className="text-sm text-muted-foreground sm:col-span-2">
              Not found in the posting — add it so it prints on the letter.
            </p>
          )}
          <div className="space-y-1">
            <Label htmlFor="rcpt-company">Company</Label>
            <Input id="rcpt-company" {...register('company')} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="rcpt-contact">Contact name</Label>
            <Input id="rcpt-contact" {...register('contact_name')} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="rcpt-address">Address</Label>
            <Input id="rcpt-address" {...register('address')} />
          </div>
          {edit.isError && (
            <div className="sm:col-span-2">
              <ErrorMessage error={edit.error} />
            </div>
          )}
          <div className="sm:col-span-2">
            <Button type="submit" size="sm" loading={edit.isPending}>
              Save recipient
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
