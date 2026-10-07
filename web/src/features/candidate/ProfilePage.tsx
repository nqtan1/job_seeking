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
import { useExtractProfile, useProfile } from './api'
import { ProfileForm } from './ProfileForm'
import { ProfileView } from './ProfileView'

const STEPS = [
  'Reading your CV…',
  'Finding your experience and skills…',
  'Structuring your profile…',
]

export function ProfilePage() {
  const profile = useProfile()
  const extract = useExtractProfile()
  const file = useRef<HTMLInputElement>(null)
  const [editing, setEditing] = useState(false)
  const [replacing, setReplacing] = useState(false)

  if (profile.isPending)
    return (
      <Page title="Profile">
        <ListSkeleton rows={4} />
      </Page>
    )
  if (profile.isError)
    return (
      <Page title="Profile">
        <div className="space-y-2">
          <ErrorMessage error={profile.error} />
          <Button variant="outline" onClick={() => profile.refetch()}>
            Retry
          </Button>
        </div>
      </Page>
    )

  const upload = (
    <Card>
      <CardHeader>
        <CardTitle>{profile.data ? 'Replace your CV' : 'Start with your CV'}</CardTitle>
        <CardDescription>
          Upload a PDF, DOCX or image. We extract your profile; you review and edit it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Label htmlFor="cv">CV file</Label>
        <Input
          id="cv"
          type="file"
          accept=".pdf,.docx,image/*"
          ref={file}
          disabled={extract.isPending}
        />
        {extract.isError && <ErrorMessage error={extract.error} />}
        {extract.isPending && <StepProgress steps={STEPS} />}
        <Button
          disabled={extract.isPending}
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
          <FileUp />
          {extract.isPending ? 'Extracting your profile…' : 'Extract profile'}
        </Button>
      </CardContent>
    </Card>
  )

  return (
    <Page
      title="Profile"
      description={
        profile.data
          ? editing
            ? 'Review and edit what we know about you.'
            : 'This is what we use to match jobs and write your letters.'
          : 'Let’s build your profile.'
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
                Update CV
              </Button>
              <Button
                onClick={() => {
                  setReplacing(false)
                  setEditing(true)
                }}
              >
                <Pencil />
                Edit profile
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
            title="No profile yet"
            description="Your CV powers job matching, letters and coaching."
          />
          {upload}
        </div>
      )}
    </Page>
  )
}
