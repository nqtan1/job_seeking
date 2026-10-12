import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useLatestFit } from '@/features/fit/api'
import { useMotivationQuestions } from './api'

const MAX_HIGHLIGHTS = 5
const MAX_ANSWER = 800
// An answer shorter than this is a slogan, not a reason (a recruiter reads straight past it).
const REAL_ANSWER_CHARS = 40

type Answer = { question: string; answer: string }

/** The candidate's own voice for the letter. The AI asks three questions about THIS job; the
 *  answers are what makes the letter personal. Without them the letter stays factual, and
 *  this block says so plainly instead of pretending. Also: tap the strengths to put forward. */
export function MotivationBlock({
  own,
  jobId,
  language,
  highlights,
  note,
  onHighlights,
  onNote,
  onAnswers,
}: {
  /** The user writes the letter: their text is kept word for word. */
  own: boolean
  jobId: string
  language: 'fr' | 'en'
  highlights: string[]
  note: string
  onHighlights: (v: string[]) => void
  onNote: (v: string) => void
  /** Called with every question and the current text of each answer. */
  onAnswers: (v: Answer[]) => void
}) {
  const fit = useLatestFit(jobId)
  const ask = useMotivationQuestions()
  const [texts, setTexts] = useState<string[]>([])
  const questions = ask.data?.questions ?? []
  const strengths = fit.data?.data.strengths ?? []
  const real = texts.filter((t) => t.trim().length >= REAL_ANSWER_CHARS).length
  const noteIsReal = note.trim().length >= REAL_ANSWER_CHARS
  const enough = real >= 2 || (real >= 1 && noteIsReal)

  const toggle = (s: string) =>
    onHighlights(
      highlights.includes(s)
        ? highlights.filter((h) => h !== s)
        : [...highlights, s].slice(0, MAX_HIGHLIGHTS),
    )
  const setText = (i: number, text: string) => {
    const next = questions.map((_, n) => (n === i ? text : (texts[n] ?? '')))
    setTexts(next)
    onAnswers(questions.map((q, n) => ({ question: q.question, answer: next[n] })))
  }

  return (
    <div className="space-y-4 sm:col-span-3">
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

      <div className="space-y-2">
        <Label>Why you want this job: in your own words</Label>
        <p className="text-sm text-muted-foreground">
          A recruiter decides on this part. Three short questions, specific to this job and your
          profile; answer with real details (a name, a moment, a reason).
        </p>
        {questions.length === 0 && (
          <Button
            type="button"
            variant="outline"
            disabled={!jobId || ask.isPending}
            aria-busy={ask.isPending}
            onClick={() =>
              ask.mutate(
                { job_id: jobId, language },
                {
                  onSuccess: (r) => {
                    setTexts([])
                    onAnswers(r.questions.map((q) => ({ question: q.question, answer: '' })))
                  },
                },
              )
            }
          >
            {ask.isPending ? 'Preparing your questions…' : 'Ask me 3 questions about this job'}
          </Button>
        )}
        {ask.isError && <ErrorMessage error={ask.error} />}
        {questions.map((q, i) => (
          <div key={q.question} className="space-y-1">
            <Label htmlFor={`answer-${i}`}>
              {i + 1}. {q.question}
            </Label>
            <Textarea
              id={`answer-${i}`}
              rows={3}
              maxLength={MAX_ANSWER}
              value={texts[i] ?? ''}
              onChange={(e) => setText(i, e.target.value)}
              aria-describedby={`answer-hint-${i}`}
            />
            <p id={`answer-hint-${i}`} className="text-xs text-muted-foreground">
              {q.hint}
            </p>
          </div>
        ))}
        {questions.length > 0 && (
          <div className="space-y-1">
            <Label htmlFor="motivation">
              {own
                ? 'Anything else, in your own words (kept exactly as you write it)'
                : 'Anything else you want the recruiter to know (optional)'}
            </Label>
            <Textarea
              id="motivation"
              rows={3}
              maxLength={1500}
              value={note}
              onChange={(e) => onNote(e.target.value)}
            />
          </div>
        )}
        {!enough && (
          <p
            role="status"
            className="rounded-md border border-dashed border-amber-500/60 bg-amber-500/5 p-2 text-sm"
          >
            {questions.length === 0
              ? 'No personal motivation yet. Without it the letter stays factual and a recruiter will notice. Answer the questions to make it yours.'
              : 'Answer at least two questions with a real detail (a few words are not enough). Otherwise the letter stays factual.'}
          </p>
        )}
      </div>
    </div>
  )
}
