import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { ContractPicker } from '@/components/ContractPicker'

function Harness({
  start = null,
  spy,
}: {
  start?: string | null
  spy: (v: string | null) => void
}) {
  const [value, setValue] = useState<string | null>(start)
  return (
    <ContractPicker
      value={value}
      onChange={(v) => {
        setValue(v)
        spy(v)
      }}
    />
  )
}

test('tick several contracts, clear to all, and type other codes', async () => {
  const user = userEvent.setup()
  const spy = vi.fn()
  render(<Harness spy={spy} />)
  expect(screen.getByRole('button', { name: 'All contracts' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )

  await user.click(screen.getByRole('button', { name: 'CDI' }))
  await user.click(screen.getByRole('button', { name: 'CDD' }))
  expect(spy).toHaveBeenLastCalledWith('CDI,CDD')
  expect(screen.getByRole('button', { name: 'All contracts' })).toHaveAttribute(
    'aria-pressed',
    'false',
  )

  await user.type(screen.getByLabelText('Other contract codes'), 'cce, rep')
  expect(spy).toHaveBeenLastCalledWith('CDI,CDD,CCE,REP')

  await user.click(screen.getByRole('button', { name: 'CDI' })) // untick one
  expect(spy).toHaveBeenLastCalledWith('CDD,CCE,REP')

  await user.click(screen.getByRole('button', { name: 'All contracts' }))
  expect(spy).toHaveBeenLastCalledWith(null)
  expect(screen.getByLabelText('Other contract codes')).toHaveValue('')
})

test('an existing value is shown as ticked chips and other codes', () => {
  render(<Harness start="CDI,SAI,CCE" spy={vi.fn()} />)

  expect(screen.getByRole('button', { name: 'CDI' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: 'Seasonal' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: 'CDD' })).toHaveAttribute('aria-pressed', 'false')
  expect(screen.getByLabelText('Other contract codes')).toHaveValue('CCE')
})
