import { zodResolver } from '@hookform/resolvers/zod'
import { useFieldArray, useForm, type FieldPath } from 'react-hook-form'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/lib/toast'
import { useUpdateProfile, type Profile } from './api'
import { profileSchema, toForm, toPatch, type FormValues } from './form'

const PERSONAL = ['name', 'email', 'phone', 'address', 'linkedin', 'github', 'website'] as const
const EXPERIENCE = ['job_title', 'company', 'start_date', 'end_date'] as const
const FORMATION = ['degree', 'field', 'institution'] as const

export function ProfileForm({
  profile,
  onSaved,
  onCancel,
}: {
  profile: Profile
  onSaved?: () => void
  onCancel?: () => void
}) {
  const save = useUpdateProfile()
  const { register, control, handleSubmit, formState } = useForm<FormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: toForm(profile),
  })
  const exp = useFieldArray({ control, name: 'experiences' })
  const edu = useFieldArray({ control, name: 'formations' })
  const skills = useFieldArray({ control, name: 'skills' })
  const { errors } = formState

  const field = (path: FieldPath<FormValues>, label: string) => (
    <div className="space-y-1" key={path}>
      <Label htmlFor={path}>{label}</Label>
      <Input id={path} {...register(path)} />
    </div>
  )
  const NAMES: Record<string, string> = { linkedin: 'LinkedIn', github: 'GitHub' }
  const label = (k: string) => NAMES[k] ?? k.replace('_', ' ').replace(/^./, (c) => c.toUpperCase())

  return (
    <form
      onSubmit={handleSubmit((v) =>
        save.mutate(toPatch(v), {
          onSuccess: () => {
            toast('Profile saved.')
            onSaved?.()
          },
        }),
      )}
      className="space-y-6"
      noValidate
    >
      <Card>
        <CardHeader>
          <CardTitle>Personal information</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {PERSONAL.map((k) => field(`personal_info.${k}`, label(k)))}
          {errors.personal_info?.name && (
            <p role="alert" className="text-sm text-destructive">
              {errors.personal_info.name.message}
            </p>
          )}
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="summary">Summary</Label>
            <Textarea id="summary" rows={4} {...register('summary')} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Experience</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {exp.fields.map((f, i) => (
            <fieldset
              key={f.id}
              className="grid gap-4 border-b pb-6 last:border-0 last:pb-0 sm:grid-cols-2"
            >
              <legend className="sr-only">Experience {i + 1}</legend>
              {EXPERIENCE.map((k) => field(`experiences.${i}.${k}`, `${label(k)} (${i + 1})`))}
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor={`experiences.${i}.description`}>Description ({i + 1})</Label>
                <Textarea
                  id={`experiences.${i}.description`}
                  rows={3}
                  {...register(`experiences.${i}.description`)}
                />
              </div>
              {(errors.experiences?.[i]?.job_title || errors.experiences?.[i]?.company) && (
                <p role="alert" className="text-sm text-destructive">
                  Job title and company are required.
                </p>
              )}
              <Button type="button" variant="outline" size="sm" onClick={() => exp.remove(i)}>
                Remove experience {i + 1}
              </Button>
            </fieldset>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              exp.append({
                job_title: '',
                company: '',
                start_date: '',
                end_date: '',
                description: '',
              })
            }
          >
            Add experience
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Education</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {edu.fields.map((f, i) => (
            <fieldset
              key={f.id}
              className="grid gap-4 border-b pb-6 last:border-0 last:pb-0 sm:grid-cols-3"
            >
              <legend className="sr-only">Education {i + 1}</legend>
              {FORMATION.map((k) => field(`formations.${i}.${k}`, `${label(k)} (${i + 1})`))}
              {(errors.formations?.[i]?.degree || errors.formations?.[i]?.institution) && (
                <p role="alert" className="text-sm text-destructive">
                  Degree and institution are required.
                </p>
              )}
              <Button type="button" variant="outline" size="sm" onClick={() => edu.remove(i)}>
                Remove education {i + 1}
              </Button>
            </fieldset>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() => edu.append({ degree: '', field: '', institution: '' })}
          >
            Add education
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Skills</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            {skills.fields.map((f, i) => (
              <div key={f.id} className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  <Label htmlFor={`skills.${i}.name`}>Skill {i + 1}</Label>
                  <Input id={`skills.${i}.name`} {...register(`skills.${i}.name`)} />
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => skills.remove(i)}>
                  Remove skill {i + 1}
                </Button>
              </div>
            ))}
          </div>
          {errors.skills && (
            <p role="alert" className="text-sm text-destructive">
              Skill names cannot be empty.
            </p>
          )}
          <Button type="button" variant="outline" onClick={() => skills.append({ name: '' })}>
            Add skill
          </Button>
        </CardContent>
      </Card>

      <div className="sticky bottom-0 -mx-6 -mb-6 flex items-center justify-end gap-3 border-t bg-background/90 px-6 py-3 backdrop-blur">
        {save.isError && <ErrorMessage error={save.error} />}
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save profile'}
        </Button>
      </div>
    </form>
  )
}
