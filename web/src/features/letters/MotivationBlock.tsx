import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useLatestFit } from '@/features/fit/api'

const MAX_HIGHLIGHTS = 5

// Starters the candidate taps to begin a sentence in their own words.
const STARTERS = [
  'What attracts me to this role is ',
  'What I want to bring is ',
  'A project of mine that connects me to this job: ',
]

/** The candidate's own voice for the letter: tap the strengths to put forward (from the fit
 *  analysis) and say, in their words, why this role. Controlled by the letter form. */
export function MotivationBlock({
  own,
  jobId,
  highlights,
  motivation,
  onHighlights,
  onMotivation,
}: {
  /** The user writes the letter: their text is kept word for word. */
  own: boolean
  jobId: string
  highlights: string[]
  motivation: string
  onHighlights: (v: string[]) => void
  onMotivation: (v: string) => void
}) {
  const fit = useLatestFit(jobId)
  const strengths = fit.data?.data.strengths ?? []
  const toggle = (s: string) =>
    onHighlights(
      highlights.includes(s)
        ? highlights.filter((h) => h !== s)
        : [...highlights, s].slice(0, MAX_HIGHLIGHTS),
    )
  return (
    <div className="space-y-3 sm:col-span-3">
      <div className="space-y-1">
        <Label>Why you fit this job</Label>
        {strengths.length > 0 ? (
          <>
            <p className="text-sm text-muted-foreground">
              Tap up to {MAX_HIGHLIGHTS} strengths to{' '}
              {own ? 'get ideas about' : 'put forward in the letter'}.
            </p>
            <div className="flex flex-wrap gap-2">
              {strengths.map((s) => (
                <Button
                  key={s}
                  type="button"
                  size="sm"
                  variant={highlights.includes(s) ? 'default' : 'outline'}
                  aria-pressed={highlights.includes(s)}
                  onClick={() => toggle(s)}
                  className="h-auto whitespace-normal py-1 text-left"
                >
                  {s}
                </Button>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            {jobId
              ? 'A fit check runs automatically so the letter shows why you match this job.'
              : 'Choose a job to see your strengths for it.'}
          </p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="motivation">
          {own
            ? 'Your own words (kept exactly as you write them)'
            : 'Your motivation, in your own words'}
        </Label>
        <div className="flex flex-wrap gap-2">
          {STARTERS.map((s) => (
            <Button
              key={s}
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onMotivation(`${motivation}${motivation ? '\n' : ''}${s}`)}
            >
              {s.trim().replace(/[:]$/, '')}…
            </Button>
          ))}
        </div>
        <Textarea
          id="motivation"
          rows={4}
          maxLength={1500}
          value={motivation}
          onChange={(e) => onMotivation(e.target.value)}
          placeholder="Why this company and this role? What drives you? Only what is true for you: the letter will use your words."
        />
      </div>
    </div>
  )
}
