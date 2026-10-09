// Typy lustrzane wobec schematow Pydantic backendu (patrz backend/app/modules/*/schemas.py).
// Trzymane recznie w synchronizacji - backend nie generuje jeszcze klienta z OpenAPI (mozliwe
// rozszerzenie w przyszlosci, patrz docs/RAPORT_ETAP_8.md).

export type Rola = 'admin' | 'magazynier'

export type Dzial = 'elektryka' | 'hydraulika'

export interface CurrentUser {
  id: string
  email: string
  rola: Rola
  magazyny_dostepne: string[]
  active: boolean
}

export interface UserDocumentStats {
  user_id: string
  email: string
  dokumenty: number
  dokumenty_potwierdzone: number
  dokumenty_historyczne_szacowane: number
  korekta_historyczna_pln: number
  minuty_zaoszczedzone: number
  pieniadze_zaoszczedzone: number
}

export interface DailyUserDocumentStats {
  email: string
  dokumenty: number
  minuty_zaoszczedzone: number
  pieniadze_zaoszczedzone: number
}

export interface DailyDocumentStats {
  data: string
  per_user: DailyUserDocumentStats[]
  dokumenty: number
  minuty_zaoszczedzone: number
  pieniadze_zaoszczedzone: number
}

export interface DocumentStats {
  per_user: UserDocumentStats[]
  daily: DailyDocumentStats[]
  razem_dokumenty: number
  razem_dokumenty_potwierdzone: number
  razem_dokumenty_historyczne_szacowane: number
  korekta_historyczna_pln: number
  data_od: string
  razem_minuty_zaoszczedzone: number
  razem_pieniadze_zaoszczedzone: number
  minuty_na_dokument: number
  stawka_pln_za_h: number
}

export interface SystemServiceStatus {
  ok: boolean
  detail: string | null
}

export interface SystemWorkerStatus {
  online: boolean
  node: string | null
}

export interface SystemQueueStatus {
  length: number
}

export interface SystemCooldownStatus {
  label: string
  model: string
  remaining_seconds: number
}

export interface SystemRecentDocumentTiming {
  document_id: string
  numer_projektu: string | null
  created_at: string
  duration_ms: number | null
}

export interface SystemAlert {
  severity: 'warning' | 'error'
  code: string
  message: string
}

export interface SystemStatus {
  generated_at: string
  overall: 'ok' | 'warning' | 'error'
  services: Record<string, SystemServiceStatus>
  workers: Record<string, SystemWorkerStatus>
  queues: Record<string, SystemQueueStatus>
  backup_last_success: string | null
  backup_age_hours: number | null
  backup_ok: boolean
  jev_enabled: boolean
  jev_mode: string
  jev_model: string
  cooldowns: SystemCooldownStatus[]
  avg_last10_ms: number | null
  last_document_ms: number | null
  recent_documents: SystemRecentDocumentTiming[]
  documents_error_24h: number
  ai_failed_events_24h: number
  alerts: SystemAlert[]
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

export interface AliasSuggestion {
  id: string
  dzial: Dzial
  target_kod: string
  target_nazwa: string | null
  alias_text: string
  status: 'pending' | 'approved' | 'rejected'
  source_document_id: string | null
  source_item_id: string | null
  created_by_id: string | null
  resolved_by_id: string | null
  created_at: string
  resolved_at: string | null
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
  // Ilosc ustalona przez druga, mniej pewna probe odczytu (dodatkowa kontrola AI dla pozycji,
  // ktorych glowny model nie odczytal pewnie), nie przez glowny model OCR - patrz
  // backend/app/modules/documents/tasks.py: _verify_ambiguous_items().
  ilosc_z_dodatkowej_kontroli: boolean
}

export interface AITraceEvent {
  status: 'queued' | 'attempt' | 'skipped' | 'rejected' | 'selected' | 'failed' | 'no_result' | 'completed'
  stage: string | null
  provider: string | null
  model: string | null
  label: string | null
  reason: string | null
  step: number | null
  total_steps: number | null
  duration_ms: number | null
  attempt: number | null
  target?: string | null
  created_at: string
}

export interface JevShadowItem {
  item_id: string
  rozpoznana_nazwa: string
  matcher_kod: string | null
  jev_kod: string | null
  agrees: boolean
  matcher_in_shortlist: boolean
  confidence: number | null
  model: string | null
  duration_ms: number
  applied: boolean | null
  locked_by_special_rule: boolean
  cleared_weak_match: boolean
  rejected_by_poles: boolean
}

export interface JevShadowSummary {
  mode: 'shadow' | 'active' | string
  ready: boolean
  complete: boolean
  expected_items: number
  pozycje_ocenione: number
  zgodne: number
  rozbieznosci: number
  zgodnosc_proc: number | null
  duration_ms: number | null
  items: JevShadowItem[]
}

export interface DocumentDetail {
  id: string
  status: DocumentStatus
  numer_projektu: string | null
  // Odczytane z naglowka formularza przez OCR (2026-09-17) - informacyjne, edytowalne recznie
  // (PATCH /documents/{id}/metadane), NIE wchodza do generowanego pliku TXT dla Optimy.
  pracownik: string | null
  numer_plomby: string | null
  source_type: string
  magazyn: string | null
  dzial: Dzial | null
  dzial_confidence: number | null
  original_filename: string
  used_provider: string | null
  rejected_count: number
  error_message: string | null
  ai_trace: AITraceEvent[]
  created_at: string
  items: DocumentItem[]
  // Czy dokument ma aktywny link Optima (2026-09-17) - sam token/URL NIGDY nie wraca stad,
  // tylko z odpowiedzi POST /documents/{id}/optima-link (patrz OptimaLink ponizej).
  optima_link_active: boolean
}

export interface OptimaLink {
  url: string
}

export interface DocumentCreated {
  id: string
  status: DocumentStatus
}

export interface DocumentItemUpdate {
  ilosc_finalna?: number | null
  match_kod?: string | null
}

export interface MetadaneUpdate {
  pracownik?: string | null
  numer_plomby?: string | null
  numer_projektu?: string | null
}

export interface DocumentItemAdd {
  match_kod: string
  ilosc_finalna: number
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

export type DocumentReportStatus = 'open' | 'resolved'

export interface DocumentReport {
  id: string
  document_id: string
  document_original_filename: string
  reported_by_email: string
  opis: string
  status: DocumentReportStatus
  created_at: string
  resolved_at: string | null
}

export interface DocumentReportCreate {
  opis: string
}
