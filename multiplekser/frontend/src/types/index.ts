// Typy lustrzane wobec schematow Pydantic backendu (patrz backend/app/modules/*/schemas.py).
// Trzymane recznie w synchronizacji - backend nie generuje jeszcze klienta z OpenAPI (mozliwe
// rozszerzenie w przyszlosci, patrz docs/RAPORT_ETAP_8.md).

export type Rola = 'admin' | 'elektryk'

export type Dzial = 'elektryka' | 'hydraulika'

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
  dzial: Dzial
}

// `dzial` nie jest czescia body zadania POST/PUT /products (przekazywany jako query param,
// domyslnie "elektryka" po stronie backendu) - katalog administracyjny w UI wciaz zarzadza
// wylacznie Elektryka, patrz docs/RAPORT_ETAP_HYDRAULIKA_2.md.
export type ProductInput = Omit<Product, 'kod' | 'dzial'> & { kod?: string }

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
  dzial: Dzial | null
  dzial_confidence: number | null
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

export interface UserInput {
  email: string
  rola: Rola
  magazyny_dostepne: string[]
  active: boolean
}

export type UserCreateInput = Omit<UserInput, 'active'> & { password: string }

export interface GenerateRequest {
  first_wydawka: boolean
}
