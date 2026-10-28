import { FileUp, Pencil } from 'lucide-react'
import { useRef, useState } from 'react'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StepProgress } from '@/components/StepProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useT } from '@/i18n'
import { useExtractProfile, useProfile } from './api'
import { ProfileForm } from './ProfileForm'
import { ProfileView } from './ProfileView'

export function ProfilePage() {
  const t = useT()
  const steps = [t('candidate.p.step1'), t('candidate.p.step2'), t('candidate.p.step3')]
  const profile = useProfile()
  const extract = useExtractProfile()
  const file = useRef<HTMLInputElement>(null)
  const [editing, setEditing] = useState(false)
  const [replacing, setReplacing] = useState(false)

  if (profile.isPending)
    return (
      <Page title={t('candidate.p.title')}>
        <ListSkeleton rows={4} />
      </Page>
    )
  if (profile.isError)
    return (
      <Page title={t('candidate.p.title')}>
        <div className="space-y-2">
          <ErrorMessage error={profile.error} />
          <Button variant="outline" onClick={() => profile.refetch()}>
            {t('candidate.p.retry')}
          </Button>
        </div>
      </Page>
    )

  const upload = (
    <Card>
      <CardHeader>
        <CardTitle>{profile.data ? t('candidate.p.replace') : t('candidate.p.start')}</CardTitle>
        <CardDescription>{t('candidate.p.upload_hint')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Label htmlFor="cv">{t('candidate.p.cv_file')}</Label>
        <Input
          id="cv"
          type="file"
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
          ref={file}
          disabled={extract.isPending}
        />
        {extract.isError && <ErrorMessage error={extract.error} />}
        {extract.isPending && <StepProgress steps={steps} />}
        <Button
          loading={extract.isPending}
          onClick={() => {
            const f = file.current?.files?.[0]
            if (f)
              extract.mutate(f, {
                onSuccess: () => {
                  // A fresh extraction is reviewed in the form before it is trusted.
                  setReplacing(false)
                  setEditing(true)
                },
              })
          }}
        >
          {!extract.isPending && <FileUp />}
          {extract.isPending ? t('candidate.p.extracting') : t('candidate.p.extract')}
        </Button>
      </CardContent>
    </Card>
  )

  return (
    <Page
      title={t('candidate.p.title')}
      description={
        profile.data
          ? editing
            ? t('candidate.p.desc_edit')
            : t('candidate.p.desc_view')
          : t('candidate.p.desc_new')
      }
    >
      {profile.data ? (
        editing ? (
          <div className="mx-auto max-w-3xl">
            <ProfileForm
              key={profile.data.document_id ?? profile.data.id}
              profile={profile.data}
              onSaved={() => setEditing(false)}
              onCancel={() => setEditing(false)}
            />
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-4">
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="outline" onClick={() => setReplacing((r) => !r)}>
                <FileUp />
                {t('candidate.p.update_cv')}
              </Button>
              <Button
                onClick={() => {
                  setReplacing(false)
                  setEditing(true)
                }}
              >
                <Pencil />
                {t('candidate.p.edit')}
              </Button>
            </div>
            {replacing && upload}
            <ProfileView profile={profile.data} />
          </div>
        )
      ) : (
        <div className="mx-auto max-w-xl space-y-6 pt-6">
          <EmptyState
            icon={FileUp}
            title={t('candidate.p.empty_title')}
            description={t('candidate.p.empty_desc')}
          />
          {upload}
        </div>
      )}
    </Page>
  )
}
