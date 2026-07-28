import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MatchQualityChip } from './MatchQualityChip'

describe('MatchQualityChip', () => {
  it.each([
    ['ok', 'OK'],
    ['warn', 'Do sprawdzenia'],
    ['bad', 'Brak dopasowania'],
    ['excluded', 'Wykluczone'],
  ])('renderuje poprawna etykiete dla jakosci %s', (quality, label) => {
    render(<MatchQualityChip quality={quality} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('dla nieznanej wartosci pokazuje ja bez tlumaczenia', () => {
    render(<MatchQualityChip quality="cos-nowego" />)
    expect(screen.getByText('cos-nowego')).toBeInTheDocument()
  })
})
