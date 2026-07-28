// Klient HTTP (Etap 8) - fetch wrapper z automatycznym doczepianiem tokenu i odswiezaniem go
// przy 401 (jedna proba, zeby uniknac petli przy trwale niewaznym refresh tokenie).
import { tokenStorage } from './tokenStorage'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

let refreshPromise: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = tokenStorage.getRefreshToken()
  if (!refreshToken) return false

  // Deduplikacja: kilka rownoleglych 401 nie odpala kilku rownoleglych /auth/refresh.
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (res) => {
        if (!res.ok) return false
        const data = (await res.json()) as { access_token: string }
        tokenStorage.setAccessToken(data.access_token)
        return true
      })
      .catch(() => false)
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

interface RequestOptions {
  method?: string
  body?: unknown
  formData?: FormData
  skipAuth?: boolean
}

async function rawRequest(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {}
  if (!options.skipAuth) {
    const token = tokenStorage.getAccessToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  let body: BodyInit | undefined
  if (options.formData) {
    body = options.formData
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  return fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body,
  })
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await rawRequest(path, options)

  if (response.status === 401 && !options.skipAuth && tokenStorage.getRefreshToken()) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      response = await rawRequest(path, options)
    }
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const data = (await response.json()) as { detail?: string }
      if (data.detail) detail = data.detail
    } catch {
      // odpowiedz bez cialka JSON (np. 204/pusta) - zostaje statusText
    }
    if (response.status === 401) {
      tokenStorage.clear()
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
