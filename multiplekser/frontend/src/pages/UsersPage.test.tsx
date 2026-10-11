import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { UsersPage } from './UsersPage'
import { getDocumentStats } from '../api/documents'
import type { DocumentStats } from '../types'

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('../api/users', () => ({ listUsers: vi.fn().mockResolvedValue([]), deleteUser: vi.fn() }))
vi.mock('../api/documents', () => ({ getDocumentStats: vi.fn() }))

it('refreshes completed documents and savings while the panel stays open', async () => {
  const stats: DocumentStats = {
    per_user: [], daily: [], razem_dokumenty: 325,
    razem_dokumenty_potwierdzone: 148, razem_dokumenty_historyczne_szacowane: 177,
    korekta_historyczna_pln: 1300, data_od: '2026-09-08',
    razem_minuty_zaoszczedzone: 2600, razem_pieniadze_zaoszczedzone: 2385.33,
    minuty_na_dokument: 8, stawka_pln_za_h: 55,
  }
  vi.mocked(getDocumentStats).mockResolvedValueOnce(stats).mockResolvedValue({
    ...stats, razem_dokumenty: 326, razem_minuty_zaoszczedzone: 2608,
    razem_pieniadze_zaoszczedzone: 2392.67,
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } })
  const view = render(<QueryClientProvider client={client}><UsersPage /></QueryClientProvider>)
  expect(await screen.findByText('325')).toBeInTheDocument()
  expect(screen.getByText('2385.33 zł')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByText('326')).toBeInTheDocument(), { timeout: 7000 })
  expect(screen.getByText('2392.67 zł')).toBeInTheDocument()
  view.unmount()
  client.clear()
}, 10000)
