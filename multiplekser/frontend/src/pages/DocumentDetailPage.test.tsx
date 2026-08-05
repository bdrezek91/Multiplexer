import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentDetailPage } from './DocumentDetailPage'
import * as documentsApi from '../api/documents'
import * as productsApi from '../api/products'
import type { DocumentDetail, Product } from '../types'

vi.mock('../api/documents', async () => {
  const actual = await vi.importActual<typeof import('../api/documents')>('../api/documents')
  return { ...actual, getDocument: vi.fn(), updateDocumentItem: vi.fn(), addDocumentItem: vi.fn() }
})
vi.mock('../api/products', async () => {
  const actual = await vi.importActual<typeof import('../api/products')>('../api/products')
  return { ...actual, listProducts: vi.fn() }
})
// Definicja usera musi byc wewnatrz fabryki (nie w zmiennej modulu) - vi.mock jest hoistowane
// nad importami, wiec zewnetrzna stala nie bylaby jeszcze zainicjalizowana w momencie wywolania.
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'admin@test.local', rola: 'admin', magazyny_dostepne: [], active: true },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

const documentDetail: DocumentDetail = {
  id: 'doc1',
  status: 'done',
  numer_projektu: '123',
  source_type: 'pdf',
  magazyn: null,
  dzial: 'hydraulika',
  dzial_confidence: 0.9,
  original_filename: 'wydawka.pdf',
  used_provider: 'gemini',
  rejected_count: 0,
  error_message: null,
  ai_trace: [],
  created_at: new Date().toISOString(),
  items: [
    {
      id: 'item1',
      rozpoznana_nazwa: 'Rura fi 32 50 cm',
      ilosc_wydana: 2,
      ilosc_zuzyta: null,
      ilosc_finalna: 2,
      match_kod: 'RURA FI 32 50 CM',
      match_nazwa: 'Rura fi 32 50 cm',
      match_jm: 'SZT',
      match_quality: 'ok',
      match_score: 1,
      off_form: false,
      needs_review: false,
      form_note: '',
      uwagi: '',
      confidence: 0.95,
    },
  ],
}

describe('DocumentDetailPage - przebieg AI', () => {
  beforeEach(() => {
    vi.mocked(documentsApi.getDocument).mockReset()
    vi.mocked(documentsApi.getDocument).mockResolvedValue({
      ...documentDetail,
      ai_trace: [
        {
          status: 'rejected', stage: 'full_ocr_hydraulika', provider: 'Gemini',
          model: 'gemini-3.6-flash', label: 'Gemini 3.6 Flash (klucz darmowy)',
          reason: 'API 429: limit zapytań', step: 1, total_steps: 6, duration_ms: 420,
          attempt: 1, created_at: '2026-08-05T07:00:00Z',
        },
        {
          status: 'selected', stage: 'full_ocr_hydraulika', provider: 'Gemini',
          model: 'gemini-3.5-flash-lite', label: 'Gemini 3.5 Flash Lite (klucz darmowy)',
          reason: null, step: 3, total_steps: 6, duration_ms: 1840,
          attempt: 1, created_at: '2026-08-05T07:00:02Z',
        },
        {
          status: 'no_result', stage: 'quantity_verification', provider: null,
          model: null, label: null, reason: 'Nie znaleziono ilości dla wskazanej pozycji',
          target: 'Gniazdo podwójne polskie białe', step: null, total_steps: null,
          duration_ms: null, attempt: null, created_at: '2026-08-05T07:00:03Z',
        },
      ],
    })
  })

  it('pokazuje model odrzucony z powodem oraz model ostatecznie wybrany', async () => {
    renderPage()

    expect(await screen.findByText('Przebieg AI')).toBeInTheDocument()
    expect(screen.getByText('Odrzucony')).toBeInTheDocument()
    expect(screen.getByText(/Powód: API 429: limit zapytań/)).toBeInTheDocument()
    expect(screen.getByText('Wybrany')).toBeInTheDocument()
    expect(screen.getByText(/Gemini 3.5 Flash Lite/)).toBeInTheDocument()
    expect(screen.getByText('Bez wyniku')).toBeInTheDocument()
    expect(screen.getByText(/Pozycje: Gniazdo podwójne polskie białe/)).toBeInTheDocument()
  })
})

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/documents/doc1']}>
        <Routes>
          <Route path="/documents/:id" element={<DocumentDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DocumentDetailPage - MatchKodCell', () => {
  beforeEach(() => {
    vi.mocked(documentsApi.getDocument).mockReset()
    vi.mocked(documentsApi.updateDocumentItem).mockReset()
    vi.mocked(documentsApi.addDocumentItem).mockReset()
    vi.mocked(productsApi.listProducts).mockReset()
    vi.mocked(documentsApi.getDocument).mockResolvedValue(documentDetail)
  })

  it('pozwala skasowac backspacem koniec dopasowanego kodu, zeby zobaczyc inne warianty', async () => {
    const user = userEvent.setup()
    const otherOptions: Product[] = [
      { kod: 'RURA FI 32 30 CM', nazwa: 'Rura fi 32 30 cm', jm: 'SZT', grupa: 'Rury', status: 'generyczny', atrybuty: {}, kolor_domniemany: false, aliasy: [], warianty_magazynowe: null, dzial: 'hydraulika' },
      { kod: 'RURA FI 32 100 CM', nazwa: 'Rura fi 32 100 cm', jm: 'SZT', grupa: 'Rury', status: 'generyczny', atrybuty: {}, kolor_domniemany: false, aliasy: [], warianty_magazynowe: null, dzial: 'hydraulika' },
    ]
    vi.mocked(productsApi.listProducts).mockResolvedValue(otherOptions)

    renderPage()

    const input = await screen.findByDisplayValue('RURA FI 32 50 CM')

    // Regresja: MatchKodCell budowal `value` Autocomplete jako nowy obiekt przy kazdym
    // renderze, co zmuszalo MUI do resetowania inputValue z powrotem do wybranego kodu przy
    // kazdym wcisnietym klawiszu (patrz useAutocomplete.js: `focused && !valueChange`).
    // Backspace nie mogl wiec nigdy skrocic tekstu ponizej pelnego kodu.
    await user.click(input)
    // selectOnFocus zaznacza cala tresc pola przy fokusie (standardowe zachowanie MUI
    // Autocomplete) - jawnie zwijamy zaznaczenie na koniec, zeby kolejne Backspace kasowaly
    // pojedyncze znaki od konca, a nie caly zaznaczony tekst za jednym razem.
    const inputEl = input as HTMLInputElement
    inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length)
    await user.keyboard('{Backspace}{Backspace}{Backspace}{Backspace}{Backspace}')

    await waitFor(() => expect(input).toHaveValue('RURA FI 32 '))
    await waitFor(() =>
      expect(productsApi.listProducts).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'RURA FI 32 ' }),
      ),
    )
    expect(await screen.findByText(/RURA FI 32 100 CM/)).toBeInTheDocument()
  })
})

describe('DocumentDetailPage - AddItemRow', () => {
  beforeEach(() => {
    vi.mocked(documentsApi.getDocument).mockReset()
    vi.mocked(documentsApi.addDocumentItem).mockReset()
    vi.mocked(productsApi.listProducts).mockReset()
    vi.mocked(documentsApi.getDocument).mockResolvedValue(documentDetail)
  })

  it('pozwala dodac nowa pozycje spoza OCR wybrana z katalogu wlasciwego dzialu', async () => {
    const user = userEvent.setup()
    const searchResults: Product[] = [
      { kod: 'BOJLER 80 L', nazwa: 'Bojler 80 L', jm: 'SZT', grupa: 'Grzejniki', status: 'generyczny', atrybuty: {}, kolor_domniemany: false, aliasy: [], warianty_magazynowe: null, dzial: 'hydraulika' },
    ]
    vi.mocked(productsApi.listProducts).mockResolvedValue(searchResults)
    vi.mocked(documentsApi.addDocumentItem).mockResolvedValue({
      id: 'item2', rozpoznana_nazwa: 'Bojler 80 L', ilosc_wydana: null, ilosc_zuzyta: null,
      ilosc_finalna: 2, match_kod: 'BOJLER 80 L', match_nazwa: 'Bojler 80 L', match_jm: 'SZT',
      match_quality: 'ok', match_score: 1, off_form: false, needs_review: false, form_note: '',
      uwagi: 'Dodano ręcznie', confidence: null,
    })

    renderPage()
    await screen.findByDisplayValue('RURA FI 32 50 CM')

    const searchInput = screen.getByPlaceholderText('Wybierz produkt z katalogu...')
    await user.type(searchInput, 'bojler')

    await waitFor(() =>
      expect(productsApi.listProducts).toHaveBeenCalledWith(
        expect.objectContaining({ dzial: 'hydraulika', search: 'bojler' }),
      ),
    )
    await user.click(await screen.findByText(/BOJLER 80 L/))

    const qtyInput = screen.getByPlaceholderText('Ilość')
    await user.type(qtyInput, '2')

    const addButton = screen.getByRole('button', { name: 'Dodaj pozycję' })
    await user.click(addButton)

    await waitFor(() =>
      expect(documentsApi.addDocumentItem).toHaveBeenCalledWith('doc1', {
        match_kod: 'BOJLER 80 L',
        ilosc_finalna: 2,
      }),
    )
  })
})
