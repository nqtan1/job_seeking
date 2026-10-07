import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { PlacePicker } from '@/components/PlacePicker'
import { REGIONS, filterRegions, placesLabel } from '@/lib/regions'

function Harness({
  start = null,
  spy,
}: {
  start?: string | null
  spy: (v: string | null) => void
}) {
  const [value, setValue] = useState<string | null>(start)
  return (
    <PlacePicker
      value={value}
      onChange={(v) => {
        setValue(v)
        spy(v)
      }}
    />
  )
}

test('the list starts with All France, then Île-de-France with Paris first, then the other regions', async () => {
  const user = userEvent.setup()
  render(<Harness spy={vi.fn()} />)
  expect(screen.getByRole('button', { name: /All France/ })).toBeInTheDocument() // the trigger says so too

  await user.click(screen.getByRole('button', { name: /All France/ }))

  const all = screen.getAllByRole('button', { name: 'All France' })
  expect(all[all.length - 1]).toHaveAttribute('aria-pressed', 'true') // the first row of the list
  const groups = screen.getAllByRole('group').filter((g) => g.tagName === 'FIELDSET')
  expect(groups[0]).toHaveAccessibleName(/Île-de-France/)
  expect(within(groups[0]).getAllByRole('checkbox')[0]).toHaveAccessibleName('Paris (75)')
  expect(REGIONS[0].name).toBe('Île-de-France')
  expect(groups[1]).toHaveAccessibleName(/Auvergne-Rhône-Alpes/)
})

test('tick cities, a whole region, search without accents, and go back to all of France', async () => {
  const user = userEvent.setup()
  const spy = vi.fn()
  render(<Harness spy={spy} />)
  await user.click(screen.getByRole('button', { name: /All France/ }))

  await user.click(screen.getByRole('checkbox', { name: 'Paris (75)' }))
  await user.click(screen.getByRole('checkbox', { name: 'Lyon · Rhône (69)' }))
  expect(spy).toHaveBeenLastCalledWith('75,69')

  await user.click(screen.getByRole('button', { name: 'Select all in Bretagne' }))
  expect(spy).toHaveBeenLastCalledWith('75,69,35,29,56,22')

  await user.type(screen.getByLabelText('Search places'), 'creteil')
  expect(screen.getByRole('checkbox', { name: 'Créteil · Val-de-Marne (94)' })).toBeInTheDocument()
  expect(screen.queryByRole('checkbox', { name: 'Paris (75)' })).toBeNull()
  await user.clear(screen.getByLabelText('Search places'))

  await user.click(screen.getByRole('button', { name: 'Remove Paris (75)' }))
  expect(spy).toHaveBeenLastCalledWith('69,35,29,56,22')
  const allFrance = screen.getAllByRole('button', { name: 'All France' })
  await user.click(allFrance[allFrance.length - 1])
  expect(spy).toHaveBeenLastCalledWith(null)
})

test('labels and filtering', () => {
  expect(placesLabel('75,69')).toBe('Paris (75), Lyon · Rhône (69)')
  expect(placesLabel(null)).toBe('All France')
  expect(filterRegions('lyon')[0].departments.map((x) => x.code)).toEqual(['69'])
  expect(filterRegions('Île-de-France')[0].departments).toHaveLength(8)
})
