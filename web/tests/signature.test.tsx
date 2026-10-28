import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { fit } from '@/features/signature/fit'
import { SignatureCard } from '@/features/signature/SignatureCard'
import { SignaturePanel } from '@/features/signature/SignaturePanel'
import { svgToPng } from '@/lib/svg-to-png'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PUT: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const limits = { min_width_mm: 20, max_width_mm: 60, max_height_mm: 25, min_dpi: 150 }
const sig = {
  document_id: 'd1',
  url: '/sig.png',
  width_px: 600,
  height_px: 200,
  aspect: 3,
  issues: ['sideways'],
  recommended_width_mm: 40,
  limits,
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/signature' ? { data: sig } : { data: null },
  )
})

test('fit: size alerts and the renderer shrink', () => {
  expect(fit(40, 3, 600, limits).alerts).toEqual([])
  expect(fit(20, 3, 600, limits).alerts).toContain('too_small')
  const big = fit(60, 2, 600, limits) // 30 mm tall > 25
  expect(big.alerts).toContain('too_big')
  expect(big.printedWidthMm).toBe(50)
  expect(big.shrunk).toBe(true)
  expect(fit(60, 3, 300, limits).alerts).toContain('low_resolution')
})

test('svgToPng draws on a scaled canvas and returns a PNG blob', async () => {
  const draw = vi.fn()
  const canvas = { width: 0, height: 0, getContext: () => ({ drawImage: draw }), toBlob: vi.fn() }
  canvas.toBlob.mockImplementation((cb: (b: Blob) => void) => cb(new Blob(['x'])))
  vi.spyOn(document, 'createElement').mockReturnValueOnce(canvas as unknown as HTMLElement)
  vi.stubGlobal(
    'Image',
    class {
      naturalWidth = 3200
      naturalHeight = 800
      onload?: () => void
      set src(_: string) {
        queueMicrotask(() => this.onload?.())
      }
    },
  )
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  await svgToPng(new File(['<svg/>'], 's.svg'))
  expect([canvas.width, canvas.height]).toEqual([1600, 400])
  expect(draw).toHaveBeenCalled()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

test('card: a sideways alert offers the fix, which POSTs a 90 degree rotation', async () => {
  mocks.POST.mockResolvedValue({ data: { ...sig, issues: [] } })
  renderWithApp(<SignatureCard name="Camille" />)
  expect(await screen.findByText('Looks rotated')).toBeInTheDocument()
  expect(screen.getByAltText('Your signature, as it will be printed')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Fix automatically' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/signature/rotate', { body: { degrees: 90 } }),
  )
})

test('card: choosing a file uploads it', async () => {
  mocks.GET.mockResolvedValue({ data: null })
  mocks.PUT.mockResolvedValue({ data: sig })
  const { container } = renderWithApp(<SignatureCard />)
  await screen.findByText('Choose a file')
  const file = new File(['x'], 'sig.png', { type: 'image/png' })
  fireEvent.change(container.querySelector('input[type=file]')!, { target: { files: [file] } })
  await waitFor(() => expect(mocks.PUT).toHaveBeenCalled())
})

test('panel: toggling on PATCHes the width; alerts follow the slider', async () => {
  const letter = { id: 'l1', content: { signature_image: null } } as never
  mocks.PATCH.mockResolvedValue({
    data: { id: 'l1', content: { signature_image: { width_mm: 40 } } },
  })
  renderWithApp(<SignaturePanel letter={letter} />)
  await userEvent.click(await screen.findByLabelText('Add my signature above my name'))
  await waitFor(() =>
    expect(mocks.PATCH).toHaveBeenCalledWith('/api/v1/letters/{letter_id}/signature', {
      params: { path: { letter_id: 'l1' } },
      body: { width_mm: 40 },
    }),
  )
})

test('panel: a small width shows the too_small alert', async () => {
  const letter = { id: 'l1', content: { signature_image: { width_mm: 40 } } } as never
  renderWithApp(<SignaturePanel letter={letter} />)
  const slider = await screen.findByRole('slider')
  expect(screen.queryByRole('alert')).toBeNull()
  fireEvent.change(slider, { target: { value: '20' } })
  expect(await screen.findByText(/Too small/)).toBeInTheDocument()
})
