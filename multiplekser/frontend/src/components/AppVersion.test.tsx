import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AppVersion } from './AppVersion'
import { apiRequest } from '../api/client'

vi.mock('../api/client', () => ({ apiRequest: vi.fn() }))

describe('AppVersion', () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset()
    document.title = 'Multiplekser'
  })

  it('pobiera numer z jednego endpointu VERSION, a nie ze stałej', async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({ version: '1.0.44' })
    render(<AppVersion />)
    expect(await screen.findByText('Multiplekser v1.0.44')).toBeInTheDocument()
    expect(document.title).toBe('Multiplekser v1.0.44')
    expect(apiRequest).toHaveBeenCalledWith('/version', { skipAuth: true })
  })

  it('nie pokazuje nieaktualnego numeru, gdy API jest niedostępne', async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(new Error('unavailable'))
    render(<AppVersion />)
    expect(screen.getByText('Multiplekser')).toBeInTheDocument()
    expect(screen.queryByText('Multiplekser v1.0.43')).not.toBeInTheDocument()
  })
})
