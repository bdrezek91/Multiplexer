import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusChip } from './StatusChip'

describe('StatusChip', () => {
  it.each([
    ['queued', 'W kolejce'],
    ['processing', 'Przetwarzanie'],
    ['done', 'Gotowe'],
    ['error', 'Błąd'],
  ] as const)('renderuje poprawna etykiete dla statusu %s', (status, label) => {
    render(<StatusChip status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})
