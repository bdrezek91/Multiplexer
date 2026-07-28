import { apiRequest } from './client'
import type { DocumentCreated, DocumentDetail } from '../types'

export function listDocuments(): Promise<DocumentDetail[]> {
  return apiRequest<DocumentDetail[]>('/documents')
}

export function getDocument(id: string): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${encodeURIComponent(id)}`)
}

export function uploadDocument(file: File, magazyn?: string): Promise<DocumentCreated> {
  const formData = new FormData()
  formData.append('plik', file)
  if (magazyn) formData.append('magazyn', magazyn)
  return apiRequest<DocumentCreated>('/documents', { method: 'POST', formData })
}
