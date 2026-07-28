import { apiRequest } from './client'
import type { CurrentUser, UserCreateInput, UserInput } from '../types'

export function listUsers(): Promise<CurrentUser[]> {
  return apiRequest<CurrentUser[]>('/users')
}

export function createUser(data: UserCreateInput): Promise<CurrentUser> {
  return apiRequest<CurrentUser>('/users', { method: 'POST', body: data })
}

export function updateUser(id: string, data: UserInput): Promise<CurrentUser> {
  return apiRequest<CurrentUser>(`/users/${encodeURIComponent(id)}`, { method: 'PUT', body: data })
}

export function resetPassword(id: string, newPassword: string): Promise<CurrentUser> {
  return apiRequest<CurrentUser>(`/users/${encodeURIComponent(id)}/reset-password`, {
    method: 'POST',
    body: { new_password: newPassword },
  })
}
