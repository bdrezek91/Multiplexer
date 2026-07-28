import { apiRequest, apiRequestBlob } from './client'
import type { DocumentCreated, DocumentDetail, DocumentItem, DocumentItemUpdate, GenerateRequest } from '../types'

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

export function updateDocumentItem(
  documentId: string,
  itemId: string,
  body: DocumentItemUpdate,
): Promise<DocumentItem> {
  return apiRequest<DocumentItem>(
    `/documents/${encodeURIComponent(documentId)}/items/${encodeURIComponent(itemId)}`,
    { method: 'PATCH', body },
  )
}

export async function generateDocument(
  documentId: string,
  body: GenerateRequest,
): Promise<{ blob: Blob; filename: string | null }> {
  return apiRequestBlob(`/documents/${encodeURIComponent(documentId)}/generate`, { method: 'POST', body })
}
