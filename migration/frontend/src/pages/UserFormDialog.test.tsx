import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { UserFormDialog } from './UserFormDialog'
import * as usersApi from '../api/users'
import type { CurrentUser } from '../types'

vi.mock('../api/users', async () => {
  const actual = await vi.importActual<typeof import('../api/users')>('../api/users')
  return { ...actual, createUser: vi.fn(), updateUser: vi.fn() }
})

function renderDialog(user: CurrentUser | null, isSelf = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <UserFormDialog open onClose={vi.fn()} user={user} isSelf={isSelf} />
    </QueryClientProvider>,
  )
}

describe('UserFormDialog', () => {
  beforeEach(() => {
    vi.mocked(usersApi.createUser).mockReset()
    vi.mocked(usersApi.updateUser).mockReset()
  })

  it('przy tworzeniu pozwala wybrac magazyny przyciskami i wysyla haslo', async () => {
    const user = userEvent.setup()
    vi.mocked(usersApi.createUser).mockResolvedValue({} as CurrentUser)

    renderDialog(null)

    await user.type(screen.getByLabelText(/email/i), 'nowy@test.local')
    await user.type(screen.getByLabelText(/hasło/i), 'haslo12345')
    await user.click(screen.getByRole('button', { name: 'Magazyn Zabrze' }))
    await user.click(screen.getByRole('button', { name: 'Magazyn Czekanów' }))
    await user.click(screen.getByRole('button', { name: /zapisz/i }))

    await waitFor(() => expect(usersApi.createUser).toHaveBeenCalledTimes(1))
    expect(usersApi.createUser).toHaveBeenCalledWith({
      email: 'nowy@test.local',
      password: 'haslo12345',
      rola: 'elektryk',
      magazyny_dostepne: ['Mag m-y Zabrze', 'MAGAZYN Czekanów'],
    })
  })

  it('przy edycji nie pokazuje pola hasla i wysyla PUT bez niego', async () => {
    const user = userEvent.setup()
    vi.mocked(usersApi.updateUser).mockResolvedValue({} as CurrentUser)
    const existing: CurrentUser = {
      id: 'u1', email: 'istniejacy@test.local', rola: 'elektryk',
      magazyny_dostepne: ['Mag m-y Zabrze'], active: true,
    }

    renderDialog(existing)

    expect(screen.queryByLabelText(/^hasło$/i)).not.toBeInTheDocument()
    // Magazyn "Mag m-y Zabrze" (Optima) powinien byc juz zaznaczony na przycisku "Magazyn Zabrze"
    // (przyszedl z danych uzytkownika).
    expect(screen.getByRole('button', { name: 'Magazyn Zabrze' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(screen.getByRole('button', { name: /zapisz/i }))

    await waitFor(() => expect(usersApi.updateUser).toHaveBeenCalledTimes(1))
    expect(usersApi.updateUser).toHaveBeenCalledWith('u1', {
      email: 'istniejacy@test.local',
      rola: 'elektryk',
      magazyny_dostepne: ['Mag m-y Zabrze'],
      active: true,
    })
  })

  it('dla wlasnego konta blokuje pola roli i aktywnosci', () => {
    const existing: CurrentUser = {
      id: 'self1', email: 'ja@test.local', rola: 'admin', magazyny_dostepne: [], active: true,
    }
    renderDialog(existing, true)

    expect(screen.getByLabelText(/rola/i)).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByLabelText(/aktywny/i)).toBeDisabled()
    expect(screen.getByText(/nie możesz go tu zdezaktywować/i)).toBeInTheDocument()
  })
})
