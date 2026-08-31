import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiRequest, ApiError } from './client'
import { tokenStorage } from './tokenStorage'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('apiRequest', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('dolacza token Authorization i zwraca sparsowany JSON', async () => {
    tokenStorage.setTokens('access-1', 'refresh-1')
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { kod: 'X' }))

    const result = await apiRequest<{ kod: string }>('/products/X')

    expect(result).toEqual({ kod: 'X' })
    const [, options] = fetchMock.mock.calls[0]
    expect((options?.headers as Record<string, string>)['Authorization']).toBe('Bearer access-1')
  })

  it('przy 401 probuje odswiezyc token i ponawia zadanie raz', async () => {
    tokenStorage.setTokens('stary-access', 'refresh-1')
    const fetchMock = vi.mocked(fetch)
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'wygasly token' })) // pierwsza proba
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'nowy-access' })) // /auth/refresh
      .mockResolvedValueOnce(jsonResponse(200, { kod: 'X' })) // ponowiona proba

    const result = await apiRequest<{ kod: string }>('/products/X')

    expect(result).toEqual({ kod: 'X' })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(tokenStorage.getAccessToken()).toBe('nowy-access')
  })

  it('gdy odswiezenie tokenu tez zawiedzie, rzuca ApiError 401 i czysci tokeny', async () => {
    tokenStorage.setTokens('stary-access', 'zly-refresh')
    const fetchMock = vi.mocked(fetch)
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'wygasly token' }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'nieprawidlowy refresh token' }))

    await expect(apiRequest('/products/X')).rejects.toBeInstanceOf(ApiError)
    expect(tokenStorage.getAccessToken()).toBeNull()
  })

  it('przy bledzie innym niz 401 rzuca ApiError z detail z odpowiedzi', async () => {
    tokenStorage.setTokens('access-1', 'refresh-1')
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValueOnce(jsonResponse(409, { detail: "Produkt o kodzie 'X' juz istnieje" }))

    await expect(apiRequest('/products')).rejects.toMatchObject({
      status: 409,
      detail: "Produkt o kodzie 'X' juz istnieje",
    })
  })

  it('przy 422 z tablica bledow walidacji Pydantic zwraca czytelny string, nie tablice obiektow', async () => {
    // Realny przypadek: FastAPI/Pydantic (np. Field(min_length=8)) zwraca detail jako tablice
    // {loc, msg, type}, nie zwykly string jak nasze reczne HTTPException. Bez normalizacji ta
    // tablica trafiala wprost do stanu React (UserFormDialog) i walila komponent na bialy ekran
    // przy probie wyrenderowania obiektu jako dziecka JSX.
    tokenStorage.setTokens('access-1', 'refresh-1')
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValueOnce(
      jsonResponse(422, {
        detail: [
          { loc: ['body', 'password'], msg: 'String should have at least 8 characters', type: 'string_too_short' },
        ],
      }),
    )

    await expect(apiRequest('/users')).rejects.toMatchObject({
      status: 422,
      detail: 'String should have at least 8 characters',
    })
  })

  it('bez tokenu w localStorage nie dolacza naglowka Authorization', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValueOnce(jsonResponse(200, {}))

    await apiRequest('/health')

    const [, options] = fetchMock.mock.calls[0]
    expect((options?.headers as Record<string, string>)['Authorization']).toBeUndefined()
  })
})
