import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  MenuItem,
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
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DownloadIcon from '@mui/icons-material/Download'
import { alpha } from '@mui/material/styles'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FocusEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { generateDocument, getDocument, updateDocumentItem, updateDocumentMagazyn } from '../api/documents'
import { StatusChip } from '../components/StatusChip'
import { DzialChip } from '../components/DzialChip'
import { MatchQualityChip } from '../components/MatchQualityChip'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { KNOWN_MAGAZYNY, magazynLabel } from '../constants'
import type { DocumentItem } from '../types'

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
    if (parsed !== null && Number.isNaN(parsed)) return
    if (parsed === (item.ilosc_finalna ?? null)) return
    mutation.mutate(parsed)
  }

  return (
    <TextField
      size="small"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={handleBlur}
      disabled={mutation.isPending}
      sx={{ width: 90 }}
      placeholder="-"
    />
  )
}

export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const isAdmin = user?.rola === 'admin'
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
        items.map((item) =>
          updateDocumentItem(documentId, item.id, {
            ilosc_finalna: (column === 'zuzyta' ? item.ilosc_zuzyta : item.ilosc_wydana) ?? null,
          }),
        ),
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
                    {isAdmin ? (
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
                    ) : (
                      <TextField
                        select
                        size="small"
                        value={document.magazyn ?? ''}
                        onChange={(e) => magazynMutation.mutate(e.target.value || null)}
                        disabled={magazynMutation.isPending || (user?.magazyny_dostepne ?? []).length === 0}
                        sx={{ minWidth: 200 }}
                      >
                        <MenuItem value="">Bez magazynu</MenuItem>
                        {(user?.magazyny_dostepne ?? []).map((m) => (
                          <MenuItem key={m} value={m}>
                            {magazynLabel(m)}
                          </MenuItem>
                        ))}
                      </TextField>
                    )}
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
                      <TableCell>Rozpoznana nazwa</TableCell>
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
                        // potwierdzenia - patrz docs/RAPORT_PORTABLE_1.md i historia czatu) -
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
                        <TableCell>{item.match_kod ?? '-'}</TableCell>
                        <TableCell>
                          <MatchQualityChip quality={item.match_quality} />
                        </TableCell>
                        <TableCell>{item.uwagi || '-'}</TableCell>
                      </TableRow>
                    ))}
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
