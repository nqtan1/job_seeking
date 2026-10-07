/** A 0-100 score as a ring. The number stays in the DOM text so it reads as "72/100". */
export function ScoreRing({ score, size = 96 }: { score: number; size?: number }) {
  const value = Math.max(0, Math.min(100, Math.round(score)))
  const r = 42
  const c = 2 * Math.PI * r
  const tone = value >= 70 ? 'text-success' : value >= 45 ? 'text-warning' : 'text-destructive'
  return (
    <div
      role="img"
      aria-label={`Score ${value} out of 100`}
      className="relative shrink-0"
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden>
        <circle cx="50" cy="50" r={r} fill="none" strokeWidth="8" className="stroke-muted" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - value / 100)}
          className={`stroke-current transition-[stroke-dashoffset] duration-700 ${tone}`}
        />
      </svg>
      <p className="absolute inset-0 grid place-content-center text-center leading-none">
        <span className="text-xl font-semibold">{value}</span>
        <span className="text-[0.65rem] text-muted-foreground">/100</span>
      </p>
    </div>
  )
}
