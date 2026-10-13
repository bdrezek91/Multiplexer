import { apiRequest, apiRequestBlob } from './client'
import type {
  DocumentCreated,
  DocumentDetail,
  DocumentItem,
  DocumentItemAdd,
  DocumentItemUpdate,
  DocumentReport,
  DocumentReportCreate,
  DocumentReportStatus,
  DocumentStats,
  GenerateRequest,
  JevShadowSummary,
  MetadaneUpdate,
  OptimaLink,
} from '../types'

export function listDocuments(): Promise<DocumentDetail[]> {
  return apiRequest<DocumentDetail[]>('/documents')
}

// Licznik przerobionych dokumentow per uzytkownik dla panelu administratora (2026-09-21, na
// zyczenie uzytkownika) - zestawiony z zaoszczedzonym czasem/pieniedzmi wzgledem recznego
// wprowadzania wydawki.
export function getDocumentStats(): Promise<DocumentStats> {
  return apiRequest<DocumentStats>('/documents/stats/summary')
}

export interface ClaudeUsage {
  daemon_online: boolean
  plan: string
  model: string
  effort: string
  documents_done: number
  documents_error: number
  documents_waiting: number
  total_jobs: number
  jobs_24h: number
  pages_24h: number
  jobs_7d: number
  pages_7d: number
  avg_seconds: number | null
  last_status: string | null
  last_error_kind: string | null
  last_error_at: string | null
  subscription_remaining: null
}

export function getClaudeUsage(): Promise<ClaudeUsage> {
  return apiRequest<ClaudeUsage>('/documents/claude-usage')
}

export function getDocument(id: string): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${encodeURIComponent(id)}`)
}

// `files` - jeden lub wiecej (np. dwa osobne zdjecia z telefonu tej samej papierowej wydawki,
// ktora nie zmiescila sie na jednym zdjeciu - patrz historia czatu). Wszystkie pod tym samym
// polem "plik" w FormData - backend (FastAPI) skleja powtorzone pola tej samej nazwy w liste.
export function getJevShadow(id: string): Promise<JevShadowSummary> {
  return apiRequest<JevShadowSummary>('/documents/' + encodeURIComponent(id) + '/jev-shadow')
}

export function uploadDocument(files: File[], magazyn?: string, ocrEngine: 'auto_v3' | 'standard' | 'claude_jev_test' = 'auto_v3', claudeDzial?: 'elektryka' | 'hydraulika'): Promise<DocumentCreated> {
  const formData = new FormData()
  files.forEach((file) => formData.append('plik', file))
  if (magazyn) formData.append('magazyn', magazyn)
  formData.append('ocr_engine', ocrEngine)
  if (ocrEngine === 'claude_jev_test' && claudeDzial) formData.append('claude_dzial', claudeDzial)
  return apiRequest<DocumentCreated>('/documents', { method: 'POST', formData })
}

export function updateDocumentMagazyn(documentId: string, magazyn: string | null): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${encodeURIComponent(documentId)}/magazyn`, {
    method: 'PATCH',
    body: { magazyn },
  })
}

// Reczna korekta pracownika/numeru plomby-rozdzielni odczytanych przez OCR z naglowka
// formularza (2026-09-17, na zyczenie uzytkownika) - tylko informacyjne pola.
export function updateDocumentMetadane(documentId: string, body: MetadaneUpdate): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${encodeURIComponent(documentId)}/metadane`, {
    method: 'PATCH',
    body,
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

// "Zglos problem" (2026-09-08, na zyczenie uzytkownika) - opis wolnym tekstem, link do
// dokumentu jest automatyczny (documentId w URL) - patrz backend/app/modules/documents/router.py.
export function createDocumentReport(documentId: string, body: DocumentReportCreate): Promise<DocumentReport> {
  return apiRequest<DocumentReport>(`/documents/${encodeURIComponent(documentId)}/reports`, {
    method: 'POST',
    body,
  })
}

export function listDocumentReports(status?: DocumentReportStatus): Promise<DocumentReport[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiRequest<DocumentReport[]>(`/documents/reports/list${query}`)
}

export function resolveDocumentReport(reportId: string): Promise<DocumentReport> {
  return apiRequest<DocumentReport>(`/documents/reports/${encodeURIComponent(reportId)}/resolve`, {
    method: 'PATCH',
  })
}

// Podglad/pobranie oryginalnego skanu (na zyczenie uzytkownika, 2026-09-08) - endpoint wymaga
// tokenu, wiec nie moze byc zwyklym <a href>, stad pobranie jako blob (jak generateDocument).
export function getDocumentFile(documentId: string, page = 1): Promise<{ blob: Blob; filename: string | null }> {
  return apiRequestBlob(`/documents/${encodeURIComponent(documentId)}/file?page=${page}`)
}

// Staly, anonimowy link do receptury TXT dla Comarch ERP Optima (2026-09-17) - Optima pobiera
// plik zwyklym GET, bez logowania, wiec URL nie jest chroniony tokenem sesji jak reszta API.
export function createOptimaLink(documentId: string): Promise<OptimaLink> {
  return apiRequest<OptimaLink>(`/documents/${encodeURIComponent(documentId)}/optima-link`, {
    method: 'POST',
  })
}

export function revokeOptimaLink(documentId: string): Promise<void> {
  return apiRequest<void>(`/documents/${encodeURIComponent(documentId)}/optima-link`, {
    method: 'DELETE',
  })
}
