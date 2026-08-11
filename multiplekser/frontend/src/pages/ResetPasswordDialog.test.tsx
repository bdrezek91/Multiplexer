import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ResetPasswordDialog } from './ResetPasswordDialog'
import * as usersApi from '../api/users'
import type { CurrentUser } from '../types'

vi.mock('../api/users', async () => {
  const actual = await vi.importActual<typeof import('../api/users')>('../api/users')
  return { ...actual, resetPassword: vi.fn() }
})

const testUser: CurrentUser = {
  id: 'u1', email: 'test@test.local', rola: 'magazynier', magazyny_dostepne: [], active: true,
}

function renderDialog() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ResetPasswordDialog open onClose={vi.fn()} user={testUser} />
    </QueryClientProvider>,
  )
}

describe('ResetPasswordDialog', () => {
  beforeEach(() => {
    vi.mocked(usersApi.resetPassword).mockReset()
  })

  it('wysyla nowe haslo i pokazuje potwierdzenie sukcesu', async () => {
    const user = userEvent.setup()
    vi.mocked(usersApi.resetPassword).mockResolvedValue(testUser)

    renderDialog()

    await user.type(screen.getByLabelText(/nowe hasło/i), 'nowe-haslo-123')
    await user.click(screen.getByRole('button', { name: /resetuj hasło/i }))

    await waitFor(() => expect(usersApi.resetPassword).toHaveBeenCalledWith('u1', 'nowe-haslo-123'))
    expect(await screen.findByText(/hasło zostało zmienione/i)).toBeInTheDocument()
  })
})
