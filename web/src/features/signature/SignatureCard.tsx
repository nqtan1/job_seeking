import { RotateCcw, RotateCw, Upload, Wand2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useT } from '@/i18n'
import { svgToPng } from '@/lib/svg-to-png'
import {
  useDeleteSignature,
  useRotateSignature,
  useSignature,
  useUploadSignature,
  type Signature,
} from './api'
import { SigBlock } from './SigBlock'

const MAX_BYTES = 5 * 1024 * 1024

export function SignatureCard({ name }: { name?: string | null }) {
  const t = useT()
  const sig = useSignature()
  const upload = useUploadSignature()
  const rotate = useRotateSignature()
  const del = useDeleteSignature()
  const input = useRef<HTMLInputElement>(null)
  const [localError, setLocalError] = useState<string>()
  const [fine, setFine] = useState(0)
  const [converting, setConverting] = useState(false)
  const busy = upload.isPending || rotate.isPending || del.isPending || converting

  const send = async (file: File | undefined) => {
    if (!file) return
    setLocalError(undefined)
    if (file.size > MAX_BYTES) return setLocalError(t('signature.too_large'))
    let body: Blob = file
    if (file.type === 'image/svg+xml' || /\.svg$/i.test(file.name)) {
      setConverting(true)
      try {
        body = await svgToPng(file)
      } catch {
        setConverting(false)
        return setLocalError(t('signature.svg_bad'))
      }
      setConverting(false)
    }
    upload.mutate(body)
  }
  const pick = (
    <input
      ref={input}
      type="file"
      hidden
      accept=".png,.jpg,.jpeg,.pdf,.svg,image/*,application/pdf"
      onChange={(e) => {
        void send(e.target.files?.[0])
        e.target.value = ''
      }}
    />
  )
  const error = localError ? (
    <p role="alert" className="text-sm text-destructive">
      {localError}
    </p>
  ) : (
    <ErrorMessage error={upload.error ?? rotate.error ?? del.error} />
  )
  const spin = busy ? (
    <p role="status" className="text-sm text-muted-foreground">
      {upload.isPending || converting ? t('signature.uploading') : t('signature.busy')}
    </p>
  ) : null

  const s: Signature | null | undefined = sig.data
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('signature.title')}</CardTitle>
        <CardDescription>{t('signature.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {pick}
        <ErrorMessage error={sig.error} />
        {!s ? (
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              void send(e.dataTransfer.files[0])
            }}
            className="space-y-2 rounded-lg border-2 border-dashed p-6 text-center"
          >
            <p className="text-sm">{t('signature.drop')}</p>
            <p className="text-xs text-muted-foreground">{t('signature.hint')}</p>
            <Button loading={busy} onClick={() => input.current?.click()}>
              {!busy && <Upload />}
              {t('signature.choose')}
            </Button>
          </div>
        ) : (
          <>
            <SigBlock sig={s} widthMm={s.recommended_width_mm} name={name} />
            <p className="text-xs text-muted-foreground">
              {t('signature.caption')} {t('signature.size', { w: s.recommended_width_mm })}
            </p>
            <ul className="space-y-1">
              {s.issues.map((i) => (
                <li key={i} role="alert" className="text-sm">
                  <strong>{t(`signature.issue.${i}`)}</strong> {t(`signature.issue.${i}_fix`)}
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center gap-2">
              {s.issues.includes('sideways') && (
                <Button size="sm" disabled={busy} onClick={() => rotate.mutate(90)}>
                  <Wand2 />
                  {t('signature.auto_fix')}
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => rotate.mutate(-90)}
              >
                <RotateCcw />
                {t('signature.rotate_left')}
              </Button>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => rotate.mutate(90)}>
                <RotateCw />
                {t('signature.rotate_right')}
              </Button>
            </div>
            <label className="flex flex-wrap items-center gap-2 text-sm">
              {t('signature.fine', { deg: fine })}
              <input
                type="range"
                min={-10}
                max={10}
                step={1}
                value={fine}
                disabled={busy}
                onChange={(e) => setFine(Number(e.target.value))}
                onPointerUp={() => fine && rotate.mutate(fine, { onSettled: () => setFine(0) })}
                onKeyUp={() => fine && rotate.mutate(fine, { onSettled: () => setFine(0) })}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => input.current?.click()}
              >
                {t('signature.replace')}
              </Button>
              <ConfirmButton
                label={t('signature.remove')}
                confirmLabel={t('signature.remove_confirm')}
                pending={del.isPending}
                disabled={busy}
                onConfirm={(reset) => del.mutate(undefined, { onSettled: reset })}
              />
            </div>
          </>
        )}
        {spin}
        {error}
      </CardContent>
    </Card>
  )
}
