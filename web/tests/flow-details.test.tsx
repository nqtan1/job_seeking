import { screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Details } from '@/features/helpers/ui'
import { renderWithApp } from './utils'

test('Details is folded unless asked to start open', () => {
  const { container } = renderWithApp(
    <>
      <Details>
        <p>data</p>
      </Details>
      <Details defaultOpen>
        <p>open</p>
      </Details>
    </>,
  )
  const [a, b] = container.querySelectorAll('details')
  expect(a.open).toBe(false)
  expect(b.open).toBe(true)
  expect(screen.getAllByText('Details')).toHaveLength(2)
})
