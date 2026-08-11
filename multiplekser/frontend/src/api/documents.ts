import { apiRequest, apiRequestBlob } from './client'
import type { DocumentCreated, DocumentDetail, DocumentItem, DocumentItemAdd, DocumentItemUpdate, GenerateRequest } from '../types'

export function listDocuments(): Promise<DocumentDetail[]> {
  return apiRequest<DocumentDetail[]>('/documents')
}

export function getDocument(id: string): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${encodeURIComponent(id)}`)
}

// `files` - jeden lub wiecej (np. dwa osobne zdjecia z telefonu tej samej papierowej wydawki,
// ktora nie zmiescila sie na jednym zdjeciu - patrz historia czatu). Wszystkie pod tym samym
// polem "plik" w FormData - backend (FastAPI) skleja powtorzone pola tej samej nazwy w liste.
export function uploadDocument(files: File[], magazyn?: string): Promise<DocumentCreated> {
  const formData = new FormData()
  files.forEach((file) => formData.append('plik', file))
  if (magazyn) formData.append('magazyn', magazyn)
  return apiRequest<DocumentCreated>('/documents', { method: 'POST', formData })
}

export function updateDocumentMagazyn(documentId: string, magazyn: string | null): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${encodeURIComponent(documentId)}/magazyn`, {
    method: 'PATCH',
    body: { magazyn },
  })
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

export function addDocumentItem(documentId: string, body: DocumentItemAdd): Promise<DocumentItem> {
  return apiRequest<DocumentItem>(`/documents/${encodeURIComponent(documentId)}/items`, {
    method: 'POST',
    body,
  })
}

export async function generateDocument(
  documentId: string,
  body: GenerateRequest,
): Promise<{ blob: Blob; filename: string | null }> {
  return apiRequestBlob(`/documents/${encodeURIComponent(documentId)}/generate`, { method: 'POST', body })
}
