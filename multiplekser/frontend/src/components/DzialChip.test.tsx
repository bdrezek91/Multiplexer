import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DzialChip } from './DzialChip'

describe('DzialChip', () => {
  it.each([
    ['elektryka', 'Elektryka'],
    ['hydraulika', 'Hydraulika'],
  ] as const)('renderuje poprawna etykiete dla dzialu %s', (dzial, label) => {
    render(<DzialChip dzial={dzial} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('renderuje myslnik gdy dzial jeszcze nie wykryty (null)', () => {
    render(<DzialChip dzial={null} />)
    expect(screen.getByText('–')).toBeInTheDocument()
  })
})
