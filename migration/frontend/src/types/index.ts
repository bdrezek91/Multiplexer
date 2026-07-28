// Typy lustrzane wobec schematow Pydantic backendu (patrz backend/app/modules/*/schemas.py).
// Trzymane recznie w synchronizacji - backend nie generuje jeszcze klienta z OpenAPI (mozliwe
// rozszerzenie w przyszlosci, patrz docs/RAPORT_ETAP_8.md).

export type Rola = 'admin' | 'elektryk'

export interface CurrentUser {
  id: string
  email: string
  rola: Rola
  magazyny_dostepne: string[]
  active: boolean
}

export interface Product {
  kod: string
  nazwa: string
  jm: string
  grupa: string
  status: string
  atrybuty: Record<string, unknown>
  kolor_domniemany: boolean
  aliasy: string[]
  warianty_magazynowe: Record<string, string> | null
}

export type ProductInput = Omit<Product, 'kod'> & { kod?: string }

export type DocumentStatus = 'queued' | 'processing' | 'done' | 'error'

export interface DocumentItem {
  id: string
  rozpoznana_nazwa: string
  ilosc_wydana: number | null
  ilosc_zuzyta: number | null
  ilosc_finalna: number | null
  match_kod: string | null
  match_nazwa: string | null
  match_jm: string | null
  match_quality: 'ok' | 'warn' | 'bad' | 'excluded'
  match_score: number
  off_form: boolean
  needs_review: boolean
  form_note: string
  uwagi: string
  confidence: number | null
}

export interface DocumentDetail {
  id: string
  status: DocumentStatus
  numer_projektu: string | null
  source_type: string
  magazyn: string | null
  original_filename: string
  used_provider: string | null
  rejected_count: number
  error_message: string | null
  created_at: string
  items: DocumentItem[]
}

export interface DocumentCreated {
  id: string
  status: DocumentStatus
}

export interface DocumentItemUpdate {
  ilosc_finalna?: number | null
  match_kod?: string | null
}

export type QtyMode = 'real' | 'ones'

export interface GenerateRequest {
  qty_mode: QtyMode
  first_wydawka: boolean
}
