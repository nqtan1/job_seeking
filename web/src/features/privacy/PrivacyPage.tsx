import { Link } from 'react-router'

const rows: [string, string][] = [
  [
    'Account, profile, jobs, letters, applications, coach chats, job radar',
    'While your account is active',
  ],
  [
    'Uploaded files (CV, job descriptions)',
    'While your account is active; you can delete any file at any time',
  ],
  [
    'Inactive account (no sign-in)',
    'Deleted after 24 months, with warning emails 30 and 7 days before',
  ],
  ['Temporary letter previews', '7 days'],
  ['Job search cache (public job ads)', '24 hours'],
  ['AI usage records (counts, model, timing; never your content)', '13 months'],
  ['Job radar run log (counts only)', '90 days'],
  ['Application logs', '30 days; they never contain your CV, letters or email'],
  ['Backups', 'At most 7 days: deleted data is gone from backups within 7 days'],
]

export function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl space-y-6 px-4 py-10">
      <h1 className="text-2xl font-semibold">Privacy policy</h1>
      <p className="text-sm text-muted-foreground">
        RecruitAI helps you with your job search. This page says what we keep, where, and for how
        long.
      </p>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">What we process</h2>
        <p>
          The information you give us or that you upload: your CV and the profile extracted from it,
          the jobs you save, the letters and applications you write, and your chat with the coach.
          We do not keep a photo, date of birth, gender, nationality or marital status from your CV.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Where and who</h2>
        <p>
          Your data is stored and processed in the European Union (Google Cloud, europe-west9), and
          Google Cloud acts as our processor under its data processing terms. AI features use Google
          Vertex AI in the EU. <strong>Your content is never used to train AI models.</strong>
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">How long we keep it</h2>
        <ul className="divide-y rounded-lg border">
          {rows.map(([what, howLong]) => (
            <li key={what} className="grid gap-1 p-3 sm:grid-cols-2">
              <span>{what}</span>
              <span className="text-muted-foreground">{howLong}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Your rights</h2>
        <p>
          In Settings you can export all your data as a ZIP at any time, and delete your account:
          your data and files are then deleted immediately. You also have the right of access,
          rectification, objection and complaint to the CNIL (cnil.fr).
        </p>
      </section>

      <Link to="/signin" className="text-sm text-primary underline">
        Back
      </Link>
    </main>
  )
}
