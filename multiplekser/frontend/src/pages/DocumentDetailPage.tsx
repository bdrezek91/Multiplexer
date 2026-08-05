import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DownloadIcon from '@mui/icons-material/Download'
import { alpha } from '@mui/material/styles'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FocusEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { addDocumentItem, generateDocument, getDocument, updateDocumentItem, updateDocumentMagazyn } from '../api/documents'
import { listProducts } from '../api/products'
import { StatusChip } from '../components/StatusChip'
import { DzialChip } from '../components/DzialChip'
import { MatchQualityChip } from '../components/MatchQualityChip'
import { ApiError } from '../api/client'
import { KNOWN_MAGAZYNY, magazynLabel } from '../constants'
import type { AITraceEvent, Dzial, DocumentItem, Product } from '../types'

const AI_STAGE_LABELS: Record<string, string> = {
  classification: 'Rozpoznanie działu',
  full_ocr_elektryka: 'Odczyt wydawki — Elektryka',
  full_ocr_hydraulika: 'Odczyt wydawki — Hydraulika',
  quantity_verification: 'Dodatkowa kontrola ilości',
}

const AI_STATUS: Record<string, {
  label: string
  color: 'default' | 'info' | 'warning' | 'error' | 'success'
}> = {
  attempt: { label: 'Próba', color: 'info' },
  skipped: { label: 'Pominięty', color: 'default' },
  rejected: { label: 'Odrzucony', color: 'error' },
  selected: { label: 'Wybrany', color: 'success' },
  failed: { label: 'Niepowodzenie', color: 'error' },
}

function AITracePanel({ events }: { events: AITraceEvent[] }) {
  if (events.length === 0) return null

  return (
    <Box
      sx={{
        mt: 2,
        p: 1.5,
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: (theme) => alpha(theme.palette.background.default, 0.35),
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Przebieg AI
      </Typography>
      <Stack spacing={0.75} sx={{ maxHeight: 240, overflowY: 'auto', pr: 0.5 }}>
        {events.map((event, index) => {
          const status = AI_STATUS[event.status] ?? AI_STATUS.failed
          const stage = event.stage ? (AI_STAGE_LABELS[event.stage] ?? event.stage) : 'Łańcuch AI'
          const model = event.label ?? event.model ?? 'Wszystkie modele'
          const duration = event.duration_ms !== null
            ? ` • ${(event.duration_ms / 1000).toFixed(1)} s`
            : ''
          const retry = event.attempt && event.attempt > 1 ? ` • podejście ${event.attempt}` : ''

          return (
            <Stack
              key={`${event.created_at}-${index}`}
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1}
              alignItems={{ xs: 'flex-start', sm: 'center' }}
            >
              <Chip label={status.label} color={status.color} size="small" sx={{ minWidth: 92 }} />
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2">
                  <strong>{stage}:</strong> {model}
                  <Typography component="span" variant="caption" color="text.secondary">
                    {retry}{duration}
                  </Typography>
                </Typography>
                {event.reason && (
                  <Typography variant="caption" color={event.status === 'rejected' ? 'error' : 'text.secondary'}>
                    Powód: {event.reason}
                  </Typography>
                )}
              </Box>
            </Stack>
          )
        })}
      </Stack>
    </Box>
  )
}

function QtyFinalnaCell({ documentId, item }: { documentId: string; item: DocumentItem }) {
  const queryClient = useQueryClient()
  // `key` w miejscu uzycia (ponizej) wymusza remount przy zmianie ilosc_finalna spoza tego pola
  // (np. hurtowy przelacznik "Uzyj ilosci wydanej/zuzytej") - inaczej ten lokalny stan
  // zignorowalby swiezo pobrana wartosc z serwera.
  const [value, setValue] = useState(item.ilosc_finalna ?? '')

  const mutation = useMutation({
    mutationFn: (ilosc_finalna: number | null) => updateDocumentItem(documentId, item.id, { ilosc_finalna }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents', documentId] }),
  })

  const handleBlur = (event: FocusEvent<HTMLInputElement>) => {
    const raw = event.target.value.trim()
    const parsed = raw === '' ? null : Number(raw.replace(',', '.'))
    if (parsed !== null && (!Number.isFinite(parsed) || parsed <= 0)) {
      setValue(item.ilosc_finalna ?? '')
      return
    }
    if (parsed === (item.ilosc_finalna ?? null)) return
    mutation.mutate(parsed)
  }

  return (
    <TextField
      size="small"
      type="number"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={handleBlur}
      disabled={mutation.isPending}
      sx={{ width: 90 }}
      placeholder="-"
    />
  )
}

// Wyszukiwanie i reczna zmiana dopasowanego kodu wprost z katalogu Optima - dotad "Dopasowany
// kod" byl tylko tekstem (automatyczne dopasowanie AI), bez mozliwosci poprawy gdy dopasowanie
// bylo bledne (patrz historia czatu: "rura 32 100 cm" zmapowana na najblizszy znany wariant "50
// cm", bo dokladna dlugosc nie byla jeszcze w katalogu). Backend juz wspieral PATCH match_kod
// (walidacja wzgledem katalogu) - brakowalo tylko pola w UI.
function MatchKodCell({ documentId, item, dzial }: { documentId: string; item: DocumentItem; dzial: Dzial }) {
  const queryClient = useQueryClient()
  const [inputValue, setInputValue] = useState(item.match_kod ?? '')
  const [options, setOptions] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)

  const mutation = useMutation({
    mutationFn: (match_kod: string | null) => updateDocumentItem(documentId, item.id, { match_kod }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents', documentId] }),
  })

  // Wyszukiwanie po stronie serwera (ten sam endpoint co katalog produktow), z debounce -
  // katalogi maja setki pozycji, wiec pobieranie calosci na kazde wpisane litery byloby zbedne.
  useEffect(() => {
    if (inputValue.trim().length < 2) {
      setOptions([])
      return
    }
    let active = true
    setLoading(true)
    const timeout = setTimeout(() => {
      listProducts({ dzial, search: inputValue, limit: 20 })
        .then((results) => active && setOptions(results))
        .finally(() => active && setLoading(false))
    }, 300)
    return () => {
      active = false
      clearTimeout(timeout)
    }
  }, [inputValue, dzial])

  // `defaultValue` (nie `value`!) - swiadomy wybor. MUI Autocomplete z KONTROLOWANYM `value`
  // resetuje inputValue do getOptionLabel(value) za kazdym razem, gdy referencja `value` sie
  // zmieni - a poniewaz obiekt Product budowany tu z pol item.* powstawalby na nowo przy
  // kazdym renderze (czyli przy kazdym wcisnietym klawiszu), backspace byl bez efektu: pole
  // odtwarzalo caly kod z powrotem, zanim uzytkownik zdazyl cokolwiek zobaczyc (patrz
  // useAutocomplete.js: efekt resetujacy zalezny od `value`). `defaultValue` jest odczytywane
  // przez MUI tylko raz przy montowaniu - dokladnie zgodne z istniejacym mechanizmem remountu
  // przez `key={item.id}-${item.match_kod}` w miejscu wywolania (remount = nowy "raz" po
  // kazdej faktycznej zmianie dopasowania po stronie serwera), a mid-typing nie wywoluje juz
  // zadnego resetu.
  const defaultValue: Product | null = item.match_kod
    ? ({ kod: item.match_kod, nazwa: item.match_nazwa ?? '', jm: item.match_jm ?? '' } as Product)
    : null

  return (
    <Autocomplete
      size="small"
      sx={{ minWidth: 480 }}
      options={options}
      loading={loading}
      defaultValue={defaultValue}
      inputValue={inputValue}
      isOptionEqualToValue={(option, val) => option.kod === val.kod}
      getOptionLabel={(option) => option.kod}
      filterOptions={(opts) => opts}
      onInputChange={(_, newInput) => setInputValue(newInput)}
      onChange={(_, newValue) => mutation.mutate(newValue?.kod ?? null)}
      disabled={mutation.isPending}
      noOptionsText={inputValue.trim().length < 2 ? 'Wpisz co najmniej 2 znaki' : 'Brak wyników'}
      renderOption={(props, option) => (
        <li {...props} key={option.kod}>
          {option.kod} — {option.nazwa}
        </li>
      )}
      renderInput={(params) => <TextField {...params} placeholder="Brak dopasowania" />}
    />
  )
}

// Reczne dodanie pozycji spoza OCR (np. cos pominietego na papierowej wydawce) - patrz historia
// czatu. Ten sam wzorzec wyszukiwania co MatchKodCell (search po stronie serwera, debounce), ale
// dla PUSTEGO, jeszcze nieistniejacego wiersza - stad kontrolowany `value`/`inputValue` (nie ma
// tu problemu z remountem przy kazdej zmianie, bo caly stan i tak resetuje sie po dodaniu).
function AddItemRow({ documentId, dzial }: { documentId: string; dzial: Dzial }) {
  const queryClient = useQueryClient()
  const [inputValue, setInputValue] = useState('')
  const [selected, setSelected] = useState<Product | null>(null)
  const [qty, setQty] = useState('')
  const [options, setOptions] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)

  const mutation = useMutation({
    mutationFn: (payload: { match_kod: string; ilosc_finalna: number }) => addDocumentItem(documentId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', documentId] })
      setSelected(null)
      setInputValue('')
      setQty('')
    },
  })

  useEffect(() => {
    if (inputValue.trim().length < 2) {
      setOptions([])
      return
    }
    let active = true
    setLoading(true)
    const timeout = setTimeout(() => {
      listProducts({ dzial, search: inputValue, limit: 20 })
        .then((results) => active && setOptions(results))
        .finally(() => active && setLoading(false))
    }, 300)
    return () => {
      active = false
      clearTimeout(timeout)
    }
  }, [inputValue, dzial])

  const qtyNumber = Number(qty.trim().replace(',', '.'))
  const canSubmit = Boolean(selected) && qty.trim() !== '' && Number.isFinite(qtyNumber) && qtyNumber > 0

  const handleSubmit = () => {
    if (!selected || !canSubmit) return
    mutation.mutate({ match_kod: selected.kod, ilosc_finalna: qtyNumber })
  }

  return (
    <TableRow>
      <TableCell colSpan={2}>
        <Typography variant="body2" color="text.secondary">
          Nowa pozycja
        </Typography>
      </TableCell>
      <TableCell>-</TableCell>
      <TableCell>
        <TextField
          size="small"
          type="number"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          placeholder="Ilość"
          sx={{ width: 90 }}
        />
      </TableCell>
      <TableCell>
        <Autocomplete
          size="small"
          sx={{ minWidth: 480 }}
          options={options}
          loading={loading}
          value={selected}
          inputValue={inputValue}
          isOptionEqualToValue={(option, val) => option.kod === val.kod}
          getOptionLabel={(option) => option.kod}
          filterOptions={(opts) => opts}
          onInputChange={(_, newInput) => setInputValue(newInput)}
          onChange={(_, newValue) => setSelected(newValue)}
          disabled={mutation.isPending}
          noOptionsText={inputValue.trim().length < 2 ? 'Wpisz co najmniej 2 znaki' : 'Brak wyników'}
          renderOption={(props, option) => (
            <li {...props} key={option.kod}>
              {option.kod} — {option.nazwa}
            </li>
          )}
          renderInput={(params) => <TextField {...params} placeholder="Wybierz produkt z katalogu..." />}
        />
      </TableCell>
      <TableCell>
        <IconButton
          color="primary"
          aria-label="Dodaj pozycję"
          disabled={!canSubmit || mutation.isPending}
          onClick={handleSubmit}
        >
          <AddIcon />
        </IconButton>
      </TableCell>
      <TableCell>
        {mutation.isError && (
          <Typography variant="caption" color="error">
            {mutation.error instanceof ApiError ? mutation.error.detail : 'Nie udało się dodać pozycji'}
          </Typography>
        )}
      </TableCell>
    </TableRow>
  )
}

export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const documentId = id as string
  const [firstWydawka, setFirstWydawka] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)

  const { data: document, isLoading, error } = useQuery({
    queryKey: ['documents', id],
    queryFn: () => getDocument(id as string),
    enabled: Boolean(id),
    // Polling co 2s dopoki dokument jest w trakcie przetwarzania w tle (Celery, Etap 7) -
    // zatrzymuje sie automatycznie po osiagnieciu stanu koncowego (done/error).
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'queued' || status === 'processing' ? 2000 : false
    },
  })

  const magazynMutation = useMutation({
    mutationFn: (magazyn: string | null) => updateDocumentMagazyn(documentId, magazyn),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents', documentId] }),
  })

  // "Uzyj ilosci wydanej/zuzytej" - hurtowo nadpisuje ilosc_finalna wszystkich pozycji ze
  // wskazanej kolumny (ten sam UX co selectQtyColumn() w monolicie) - reuzywa istniejacy
  // PATCH .../items/{id}, bez nowego endpointu.
  const qtyColumnMutation = useMutation({
    mutationFn: async (column: 'wydana' | 'zuzyta') => {
      const items = document?.items ?? []
      await Promise.all(
        items.map((item) => {
          const sourceQty = column === 'zuzyta' ? item.ilosc_zuzyta : item.ilosc_wydana
          const validQty = sourceQty !== null && Number.isFinite(sourceQty) && sourceQty > 0
            ? sourceQty
            : null
          return updateDocumentItem(documentId, item.id, { ilosc_finalna: validQty })
        }),
      )
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents', documentId] }),
  })

  const generateMutation = useMutation({
    mutationFn: () => generateDocument(documentId, { first_wydawka: firstWydawka }),
    onSuccess: ({ blob, filename }) => {
      // Pobranie pliku w przegladarce - odpowiednik downloadOutput() z monolitu (tam CP1250
      // kodowany po stronie klienta, tutaj gotowe bajty przychodza juz zakodowane z backendu).
      const url = URL.createObjectURL(blob)
      const a = window.document.createElement('a')
      a.href = url
      a.download = filename ?? 'receptura.txt'
      a.click()
      URL.revokeObjectURL(url)
    },
    onError: (err) => setGenerateError(err instanceof ApiError ? err.detail : 'Nie udało się wygenerować pliku'),
  })

  return (
    <Box>
      <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documents')} sx={{ mb: 2 }}>
        Powrót do listy
      </Button>

      {isLoading && <Typography>Ładowanie...</Typography>}

      {error && (
        <Alert severity="error">
          {error instanceof ApiError ? error.detail : 'Nie udało się pobrać dokumentu'}
        </Alert>
      )}

      {document && (
        <>
          <Paper sx={{ p: 2, mb: 3 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" gap={2}>
              <Box>
                <Typography variant="h6">{document.original_filename}</Typography>
                <Typography variant="body2" color="text.secondary">
                  Numer projektu: {document.numer_projektu ?? 'nieznany'}
                </Typography>
                {document.status === 'done' && (
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
                    <Typography variant="body2" color="text.secondary">
                      Magazyn:
                    </Typography>
                    <ToggleButtonGroup
                      exclusive
                      value={document.magazyn || null}
                      onChange={(_, next: string | null) => magazynMutation.mutate(next)}
                      size="small"
                      disabled={magazynMutation.isPending}
                    >
                      {KNOWN_MAGAZYNY.map((m) => (
                        <ToggleButton key={m.value} value={m.value}>
                          {m.label}
                        </ToggleButton>
                      ))}
                    </ToggleButtonGroup>
                  </Stack>
                )}
                {document.status !== 'done' && (
                  <Typography variant="body2" color="text.secondary">
                    Magazyn: {document.magazyn ? magazynLabel(document.magazyn) : '-'}
                  </Typography>
                )}
                {document.used_provider && (
                  <Typography variant="body2" color="text.secondary">
                    Rozpoznane przez: {document.used_provider}
                  </Typography>
                )}
              </Box>
              <Stack direction="row" spacing={1}>
                <DzialChip dzial={document.dzial} confidence={document.dzial_confidence} />
                <StatusChip status={document.status} />
              </Stack>
            </Stack>

            <AITracePanel events={document.ai_trace} />

            {document.status === 'processing' || document.status === 'queued' ? (
              <Alert severity="info" sx={{ mt: 2 }}>
                Dokument jest przetwarzany w tle - strona odświeży się automatycznie.
              </Alert>
            ) : null}

            {document.status === 'error' && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {document.error_message ?? 'Wystąpił nieznany błąd podczas przetwarzania'}
              </Alert>
            )}

            {document.rejected_count > 0 && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                Odrzucono {document.rejected_count} pozycji niezgodnych ze schematem (np. brak nazwy).
              </Alert>
            )}

            {!document.magazyn && document.status === 'done' && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                Nie wybrano magazynu - ostatnia kolumna w wygenerowanym pliku będzie pusta. Możesz go wybrać powyżej.
              </Alert>
            )}
          </Paper>

          {document.status === 'done' && (
            <>
              {document.items.length > 0 && (
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="body2" color="text.secondary">
                    Ilość finalna z kolumny:
                  </Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={qtyColumnMutation.isPending}
                    onClick={() => qtyColumnMutation.mutate('wydana')}
                  >
                    Wydana
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={qtyColumnMutation.isPending}
                    onClick={() => qtyColumnMutation.mutate('zuzyta')}
                  >
                    Zużyta
                  </Button>
                </Stack>
              )}
              <TableContainer component={Paper} sx={{ mb: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ minWidth: 260 }}>Rozpoznana nazwa</TableCell>
                      <TableCell>Ilość wydana</TableCell>
                      <TableCell>Ilość zużyta</TableCell>
                      <TableCell>Ilość finalna (do generowania)</TableCell>
                      <TableCell>Dopasowany kod</TableCell>
                      <TableCell>Jakość dopasowania</TableCell>
                      <TableCell>Uwagi</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {document.items.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7}>AI nie wykryło żadnych pozycji na skanie</TableCell>
                      </TableRow>
                    )}
                    {document.items.map((item) => (
                      <TableRow
                        key={item.id}
                        hover
                        // Pusta ilosc finalna dla pozycji, ktora w ogole trafila do wyniku, jest
                        // podejrzana - AI zwraca pozycje tylko gdy cos w wierszu wykryl (patrz
                        // prompt: "jesli wiersz w obu kolumnach jest pusty - pomin go
                        // calkowicie"), wiec pusta ilosc przy istniejacej pozycji czesto oznacza
                        // niejednoznaczny odczyt odreczny (np. "1" pomylona z samym ptaszkiem
                        // potwierdzenia - patrz docs/RAPORT_OCR_NIEZAWODNOSC_2.md i historia czatu) -
                        // wyroznienie ma zwrocic na to uwage osoby weryfikujacej dokument.
                        sx={
                          item.ilosc_finalna == null
                            ? { bgcolor: (theme) => alpha(theme.palette.warning.main, 0.12) }
                            : undefined
                        }
                      >
                        <TableCell>
                          {item.rozpoznana_nazwa}
                          {item.needs_review && (
                            <Chip size="small" label="do weryfikacji" sx={{ ml: 1 }} />
                          )}
                          {item.form_note && (
                            <Typography variant="caption" display="block" color="text.secondary">
                              {item.form_note}
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell>{item.ilosc_wydana ?? '-'}</TableCell>
                        <TableCell>{item.ilosc_zuzyta ?? '-'}</TableCell>
                        <TableCell>
                          <QtyFinalnaCell
                            key={`${item.id}-${item.ilosc_finalna ?? 'null'}`}
                            documentId={documentId}
                            item={item}
                          />
                        </TableCell>
                        <TableCell>
                          <MatchKodCell
                            key={`${item.id}-${item.match_kod ?? 'null'}`}
                            documentId={documentId}
                            item={item}
                            dzial={document.dzial || 'elektryka'}
                          />
                        </TableCell>
                        <TableCell>
                          <MatchQualityChip quality={item.match_quality} />
                        </TableCell>
                        <TableCell>{item.uwagi || '-'}</TableCell>
                      </TableRow>
                    ))}
                    <AddItemRow documentId={documentId} dzial={document.dzial || 'elektryka'} />
                  </TableBody>
                </Table>
              </TableContainer>

              <Paper sx={{ p: 2 }}>
                <Typography variant="subtitle1" gutterBottom>
                  Generowanie do Optima
                </Typography>
                <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                  {/* "Pierwsza wydawka" nie ma odpowiednika dla Hydrauliki - dopisywanie
                      pozycji domyslnych do kazdej receptury to koncepcja specyficzna dla
                      Elektryki, patrz generator/core_hydraulika.py. */}
                  {document.dzial !== 'hydraulika' && (
                    <FormControlLabel
                      control={
                        <Checkbox checked={firstWydawka} onChange={(e) => setFirstWydawka(e.target.checked)} />
                      }
                      label="Pierwsza wydawka (dołącz bazę materiałów)"
                    />
                  )}
                  <Button
                    variant="contained"
                    startIcon={<DownloadIcon />}
                    onClick={() => {
                      setGenerateError(null)
                      generateMutation.mutate()
                    }}
                    disabled={generateMutation.isPending}
                  >
                    Generuj
                  </Button>
                </Stack>
                {generateError && (
                  <Alert severity="error" sx={{ mt: 2 }}>
                    {generateError}
                  </Alert>
                )}
              </Paper>
            </>
          )}
        </>
      )}
    </Box>
  )
}
