import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from './LoginPage'
import { AuthProvider } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import * as authApi from '../api/auth'

vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return {
    ...actual,
    login: vi.fn(),
    fetchCurrentUser: vi.fn(),
  }
})

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/documents" element={<div>Strona dokumentow</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(authApi.login).mockReset()
    vi.mocked(authApi.fetchCurrentUser).mockReset()
  })

  it('po poprawnym logowaniu przekierowuje do /documents', async () => {
    const user = userEvent.setup()
    vi.mocked(authApi.login).mockResolvedValue(undefined)
    vi.mocked(authApi.fetchCurrentUser).mockResolvedValue({
      id: '1',
      email: 'admin@test.local',
      rola: 'admin',
      magazyny_dostepne: [],
      active: true,
    })

    renderLoginPage()

    await user.type(screen.getByLabelText(/email/i), 'admin@test.local')
    await user.type(screen.getByLabelText(/haslo/i), 'tajne-haslo')
    await user.click(screen.getByRole('button', { name: /zaloguj/i }))

    await waitFor(() => expect(screen.getByText('Strona dokumentow')).toBeInTheDocument())
    expect(authApi.login).toHaveBeenCalledWith('admin@test.local', 'tajne-haslo')
  })

  it('przy blednych danych pokazuje komunikat bledu i nie przekierowuje', async () => {
    const user = userEvent.setup()
    vi.mocked(authApi.login).mockRejectedValue(new ApiError(401, 'Nieprawidlowy email lub haslo'))

    renderLoginPage()

    await user.type(screen.getByLabelText(/email/i), 'admin@test.local')
    await user.type(screen.getByLabelText(/haslo/i), 'zle-haslo')
    await user.click(screen.getByRole('button', { name: /zaloguj/i }))

    expect(await screen.findByText('Nieprawidlowy email lub haslo')).toBeInTheDocument()
    expect(screen.queryByText('Strona dokumentow')).not.toBeInTheDocument()
  })
})
