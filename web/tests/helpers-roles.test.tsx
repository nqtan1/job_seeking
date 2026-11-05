import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InstructionsField, SpecForm } from '@/features/helpers/HelperForm'
import type { VersionSpec } from '@/features/helpers/graph'

const custom: VersionSpec = {
  role: 'custom',
  instructions: 'Write a follow-up.',
  model_tier: 'fast',
  inputs: [{ name: 'notes', label: 'Notes', required: true }],
  context_sources: [],
  output: { kind: 'text', fields: [] },
}

test('a built-in role keeps its own prompt and format: only extra preferences are editable', async () => {
  const onChange = vi.fn()
  const user = userEvent.setup()
  const { rerender } = render(<SpecForm spec={custom} onChange={onChange} />)
  expect(screen.getByText('What you give it')).toBeInTheDocument()

  await user.selectOptions(screen.getByLabelText('Type of helper'), 'letter')
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      role: 'letter',
      inputs: [],
      context_sources: ['profile', 'job', 'fit'],
    }),
  )

  rerender(<SpecForm spec={{ ...custom, role: 'letter', inputs: [] }} onChange={onChange} />)
  expect(screen.queryByText('What you give it')).not.toBeInTheDocument() // locked by the role
  rerender(<InstructionsField spec={{ ...custom, role: 'letter' }} onChange={onChange} />)
  expect(screen.getByLabelText('Your extra preferences')).toBeInTheDocument()
  rerender(<SpecForm spec={{ ...custom, role: 'letter', inputs: [] }} onChange={onChange} />)
  expect(screen.getByText(/writes a cover letter of about 200 words/)).toBeInTheDocument()
})
