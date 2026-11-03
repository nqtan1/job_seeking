import { cn } from 'cn'
import { type AvatarSpec, type Mood, PALETTES, safe } from './avatar'

type Props = {
  spec: AvatarSpec
  mood?: Mood
  size?: number
  /** Text for assistive tech. Omit when the helper's name is shown next to it (decorative). */
  label?: string
  className?: string
}

// Ears / shape per body; all drawn in a 64×64 box. Plain shapes, so it stays cheap to animate.
function Body({ body, fill, accent }: { body: number; fill: string; accent: string }) {
  const ears = (
    <>
      {body === 1 && (
        <>
          <path d="M14 22 L16 6 L28 16 Z" fill={fill} stroke={accent} strokeWidth="2" />
          <path d="M50 22 L48 6 L36 16 Z" fill={fill} stroke={accent} strokeWidth="2" />
        </>
      )}
      {body === 2 && (
        <>
          <circle cx="16" cy="14" r="7" fill={fill} stroke={accent} strokeWidth="2" />
          <circle cx="48" cy="14" r="7" fill={fill} stroke={accent} strokeWidth="2" />
        </>
      )}
      {body === 3 && (
        <>
          <ellipse cx="22" cy="9" rx="5" ry="11" fill={fill} stroke={accent} strokeWidth="2" />
          <ellipse cx="42" cy="9" rx="5" ry="11" fill={fill} stroke={accent} strokeWidth="2" />
        </>
      )}
      {body === 4 && <path d="M32 2 L40 14 L24 14 Z" fill={accent} />}
      {body === 5 && (
        <>
          <circle cx="14" cy="20" r="5" fill={accent} />
          <circle cx="50" cy="20" r="5" fill={accent} />
        </>
      )}
    </>
  )
  const shape =
    body === 6 ? (
      <rect x="9" y="12" width="46" height="46" rx="12" />
    ) : body === 7 ? (
      <path d="M32 10 C50 10 56 26 56 38 C56 52 46 58 32 58 C18 58 8 52 8 38 C8 26 14 10 32 10 Z" />
    ) : (
      <ellipse cx="32" cy="36" rx="23" ry="22" />
    )
  return (
    <>
      {ears}
      <g fill={fill} stroke={accent} strokeWidth="2">
        {shape}
      </g>
    </>
  )
}

function Eyes({ style, ink, mood }: { style: number; ink: string; mood: Mood }) {
  if (mood === 'done') {
    return (
      <g stroke={ink} strokeWidth="2.5" strokeLinecap="round" fill="none">
        <path d="M19 33 Q24 27 29 33" />
        <path d="M35 33 Q40 27 45 33" />
      </g>
    )
  }
  if (mood === 'failed') {
    return (
      <g stroke={ink} strokeWidth="2.5" strokeLinecap="round">
        <path d="M20 29 L28 37 M28 29 L20 37" />
        <path d="M36 29 L44 37 M44 29 L36 37" />
      </g>
    )
  }
  if (mood === 'skipped') {
    return (
      <g stroke={ink} strokeWidth="2.5" strokeLinecap="round">
        <path d="M19 33 H29 M35 33 H45" />
      </g>
    )
  }
  const dy = mood === 'thinking' ? -2 : 0
  const r = style === 1 ? 4.5 : style === 2 ? 3.5 : 3
  return (
    <g className="avatar-eyes" fill={ink} transform={`translate(0 ${dy})`}>
      {style === 3 ? (
        <>
          <rect x="19" y="30" width="10" height="6" rx="3" />
          <rect x="35" y="30" width="10" height="6" rx="3" />
        </>
      ) : style === 4 ? (
        <>
          <ellipse cx="24" cy="33" rx="3" ry="5" />
          <ellipse cx="40" cy="33" rx="3" ry="5" />
        </>
      ) : (
        <>
          <circle cx="24" cy="33" r={r} />
          <circle cx="40" cy="33" r={r} />
          {style === 5 && (
            <>
              <circle cx="25" cy="31.5" r="1.2" fill="#fff" />
              <circle cx="41" cy="31.5" r="1.2" fill="#fff" />
            </>
          )}
        </>
      )}
    </g>
  )
}

function Accessory({ kind, accent, ink }: { kind: number; accent: string; ink: string }) {
  switch (kind) {
    case 1:
      return (
        <g fill="none" stroke={ink} strokeWidth="2">
          <circle cx="24" cy="33" r="7" />
          <circle cx="40" cy="33" r="7" />
          <path d="M31 33 H33" />
        </g>
      )
    case 2:
      return <path d="M14 20 Q32 2 50 20 Z" fill={accent} />
    case 3:
      return (
        <g fill={accent}>
          <path d="M32 50 L22 44 V56 Z" />
          <path d="M32 50 L42 44 V56 Z" />
        </g>
      )
    case 4:
      return (
        <g stroke={ink} strokeWidth="2" fill="none">
          <path d="M32 14 V4" />
          <circle cx="32" cy="3" r="2.5" fill={accent} stroke="none" />
        </g>
      )
    case 5:
      return (
        <g fill="none" stroke={accent} strokeWidth="4" strokeLinecap="round">
          <path d="M10 34 Q10 10 32 10 Q54 10 54 34" />
        </g>
      )
    case 6:
      return <rect x="14" y="48" width="36" height="6" rx="3" fill={accent} />
    case 7:
      return <path d="M50 12 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2 Z" fill={accent} />
    default:
      return null
  }
}

/** A helper's character. Parameters in, SVG out: no uploads, no markup from the server. The mood
 *  drives CSS animations that only move transform/opacity and stop under reduced motion. */
export function Avatar({ spec, mood = 'idle', size = 40, label, className }: Props) {
  const a = safe(spec)
  const p = PALETTES[a.palette]
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      data-mood={mood}
      className={cn('avatar overflow-visible', `avatar-${mood}`, className)}
    >
      {size >= 40 && <circle cx="32" cy="34" r="31" fill={p.accent} opacity="0.14" />}
      <g className="avatar-body">
        <Body body={a.body} fill={p.fill} accent={p.accent} />
        {size >= 40 && (
          <>
            <ellipse cx="22" cy="23" rx="8" ry="4" fill="#fff" opacity="0.28" />
            <circle cx="17" cy="42" r="3.5" fill={p.accent} opacity="0.22" />
            <circle cx="47" cy="42" r="3.5" fill={p.accent} opacity="0.22" />
          </>
        )}
        <Eyes style={a.eyes} ink={p.ink} mood={mood} />
        <path
          d="M27 43 Q32 47 37 43"
          fill="none"
          stroke={p.ink}
          strokeWidth="2"
          strokeLinecap="round"
        />
        <Accessory kind={a.accessory} accent={p.accent} ink={p.ink} />
      </g>
      {mood === 'thinking' && (
        <g className="avatar-dots" fill={p.accent} aria-hidden>
          <circle cx="48" cy="6" r="2" />
          <circle cx="54" cy="3" r="2" />
          <circle cx="60" cy="0" r="2" />
        </g>
      )}
    </svg>
  )
}
