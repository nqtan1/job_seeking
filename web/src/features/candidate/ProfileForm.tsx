import { zodResolver } from '@hookform/resolvers/zod'
import { useFieldArray, useForm, type FieldPath } from 'react-hook-form'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useT, type Key } from '@/i18n'
import { toast } from '@/lib/toast'
import { useUpdateProfile, type Profile } from './api'
import { makeProfileSchema, toForm, toPatch, type FormValues } from './form'

const PERSONAL = ['name', 'email', 'phone', 'address', 'linkedin', 'github', 'website'] as const
const EXPERIENCE = ['job_title', 'company', 'start_date', 'end_date'] as const
const FORMATION = ['degree', 'field', 'institution'] as const

const LABELS: Record<string, Key> = {
  name: 'candidate.l.name',
  email: 'candidate.l.email',
  phone: 'candidate.l.phone',
  address: 'candidate.l.address',
  website: 'candidate.l.website',
  job_title: 'candidate.l.job_title',
  company: 'candidate.l.company',
  start_date: 'candidate.l.start_date',
  end_date: 'candidate.l.end_date',
  degree: 'candidate.l.degree',
  field: 'candidate.l.field',
  institution: 'candidate.l.institution',
}
const NAMES: Record<string, string> = { linkedin: 'LinkedIn', github: 'GitHub' }

export function ProfileForm({
  profile,
  onSaved,
  onCancel,
}: {
  profile: Profile
  onSaved?: () => void
  onCancel?: () => void
}) {
  const t = useT()
  const save = useUpdateProfile()
  const { register, control, handleSubmit, formState } = useForm<FormValues>({
    resolver: zodResolver(makeProfileSchema(t)),
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
  const label = (k: string) => NAMES[k] ?? t(LABELS[k])
  const numbered = (k: string, n: number) => t('candidate.numbered', { label: label(k), n })

  return (
    <form
      onSubmit={handleSubmit((v) =>
        save.mutate(toPatch(v), {
          onSuccess: () => {
            toast(t('candidate.saved'))
            onSaved?.()
          },
        }),
      )}
      className="space-y-6"
      noValidate
    >
      <Card>
        <CardHeader>
          <CardTitle>{t('candidate.h.personal')}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {PERSONAL.map((k) => field(`personal_info.${k}`, label(k)))}
          {errors.personal_info?.name && (
            <p role="alert" className="text-sm text-destructive">
              {errors.personal_info.name.message}
            </p>
          )}
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="summary">{t('candidate.h.summary')}</Label>
            <Textarea id="summary" rows={4} {...register('summary')} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('candidate.h.experience')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {exp.fields.map((f, i) => (
            <fieldset
              key={f.id}
              className="grid gap-4 border-b pb-6 last:border-0 last:pb-0 sm:grid-cols-2"
            >
              <legend className="sr-only">{t('candidate.f.experience_n', { n: i + 1 })}</legend>
              {EXPERIENCE.map((k) => field(`experiences.${i}.${k}`, numbered(k, i + 1)))}
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor={`experiences.${i}.description`}>
                  {t('candidate.f.description_n', { n: i + 1 })}
                </Label>
                <Textarea
                  id={`experiences.${i}.description`}
                  rows={3}
                  {...register(`experiences.${i}.description`)}
                />
              </div>
              {(errors.experiences?.[i]?.job_title || errors.experiences?.[i]?.company) && (
                <p role="alert" className="text-sm text-destructive">
                  {t('candidate.f.exp_required')}
                </p>
              )}
              <Button type="button" variant="outline" size="sm" onClick={() => exp.remove(i)}>
                {t('candidate.f.remove_exp', { n: i + 1 })}
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
            {t('candidate.f.add_exp')}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('candidate.h.education')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {edu.fields.map((f, i) => (
            <fieldset
              key={f.id}
              className="grid gap-4 border-b pb-6 last:border-0 last:pb-0 sm:grid-cols-3"
            >
              <legend className="sr-only">{t('candidate.f.education_n', { n: i + 1 })}</legend>
              {FORMATION.map((k) => field(`formations.${i}.${k}`, numbered(k, i + 1)))}
              {(errors.formations?.[i]?.degree || errors.formations?.[i]?.institution) && (
                <p role="alert" className="text-sm text-destructive">
                  {t('candidate.f.edu_required')}
                </p>
              )}
              <Button type="button" variant="outline" size="sm" onClick={() => edu.remove(i)}>
                {t('candidate.f.remove_edu', { n: i + 1 })}
              </Button>
            </fieldset>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() => edu.append({ degree: '', field: '', institution: '' })}
          >
            {t('candidate.f.add_edu')}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('candidate.h.skills')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            {skills.fields.map((f, i) => (
              <div key={f.id} className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  <Label htmlFor={`skills.${i}.name`}>
                    {t('candidate.f.skill_n', { n: i + 1 })}
                  </Label>
                  <Input id={`skills.${i}.name`} {...register(`skills.${i}.name`)} />
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => skills.remove(i)}>
                  {t('candidate.f.remove_skill', { n: i + 1 })}
                </Button>
              </div>
            ))}
          </div>
          {errors.skills && (
            <p role="alert" className="text-sm text-destructive">
              {t('candidate.f.skills_empty')}
            </p>
          )}
          <Button type="button" variant="outline" onClick={() => skills.append({ name: '' })}>
            {t('candidate.f.add_skill')}
          </Button>
        </CardContent>
      </Card>

      <div className="sticky bottom-0 -mx-6 -mb-6 flex items-center justify-end gap-3 border-t bg-background/90 px-6 py-3 backdrop-blur">
        {save.isError && <ErrorMessage error={save.error} />}
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            {t('candidate.f.cancel')}
          </Button>
        )}
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? t('candidate.f.saving') : t('candidate.f.save')}
        </Button>
      </div>
    </form>
  )
}
