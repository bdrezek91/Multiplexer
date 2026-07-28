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
  Typography,
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DownloadIcon from '@mui/icons-material/Download'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FocusEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { generateDocument, getDocument, updateDocumentItem } from '../api/documents'
import { StatusChip } from '../components/StatusChip'
import { MatchQualityChip } from '../components/MatchQualityChip'
import { ApiError } from '../api/client'
import type { DocumentItem, QtyMode } from '../types'

function QtyFinalnaCell({ documentId, item }: { documentId: string; item: DocumentItem }) {
  const queryClient = useQueryClient()
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
  const documentId = id as string
  const [qtyMode, setQtyMode] = useState<QtyMode>('real')
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

  const generateMutation = useMutation({
    mutationFn: () => generateDocument(documentId, { qty_mode: qtyMode, first_wydawka: firstWydawka }),
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
    onError: (err) => setGenerateError(err instanceof ApiError ? err.detail : 'Nie udalo sie wygenerowac pliku'),
  })

  return (
    <Box>
      <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documents')} sx={{ mb: 2 }}>
        Powrot do listy
      </Button>

      {isLoading && <Typography>Ladowanie...</Typography>}

      {error && (
        <Alert severity="error">
          {error instanceof ApiError ? error.detail : 'Nie udalo sie pobrac dokumentu'}
        </Alert>
      )}

      {document && (
        <>
          <Paper sx={{ p: 2, mb: 3 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" gap={2}>
              <Box>
                <Typography variant="h6">{document.original_filename}</Typography>
                <Typography variant="body2" color="text.secondary">
                  Numer projektu: {document.numer_projektu ?? 'nieznany'} · Magazyn: {document.magazyn ?? '-'}
                </Typography>
                {document.used_provider && (
                  <Typography variant="body2" color="text.secondary">
                    Rozpoznane przez: {document.used_provider}
                  </Typography>
                )}
              </Box>
              <StatusChip status={document.status} />
            </Stack>

            {document.status === 'processing' || document.status === 'queued' ? (
              <Alert severity="info" sx={{ mt: 2 }}>
                Dokument jest przetwarzany w tle - strona odswiezy sie automatycznie.
              </Alert>
            ) : null}

            {document.status === 'error' && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {document.error_message ?? 'Wystapil nieznany blad podczas przetwarzania'}
              </Alert>
            )}

            {document.rejected_count > 0 && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                Odrzucono {document.rejected_count} pozycji niezgodnych ze schematem (np. brak nazwy).
              </Alert>
            )}

            {!document.magazyn && document.status === 'done' && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                Nie wybrano magazynu przy uploadzie - ostatnia kolumna w wygenerowanym pliku bedzie pusta.
              </Alert>
            )}
          </Paper>

          {document.status === 'done' && (
            <>
              <TableContainer component={Paper} sx={{ mb: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Rozpoznana nazwa</TableCell>
                      <TableCell>Ilosc wydana</TableCell>
                      <TableCell>Ilosc zuzyta</TableCell>
                      <TableCell>Ilosc finalna (do generowania)</TableCell>
                      <TableCell>Dopasowany kod</TableCell>
                      <TableCell>Jakosc dopasowania</TableCell>
                      <TableCell>Uwagi</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {document.items.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7}>AI nie wykrylo zadnych pozycji na skanie</TableCell>
                      </TableRow>
                    )}
                    {document.items.map((item) => (
                      <TableRow key={item.id} hover>
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
                          <QtyFinalnaCell documentId={documentId} item={item} />
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
                  <TextField
                    select
                    size="small"
                    label="Ilosci"
                    value={qtyMode}
                    onChange={(e) => setQtyMode(e.target.value as QtyMode)}
                    sx={{ width: 220 }}
                  >
                    <MenuItem value="real">Rzeczywiste ilosci</MenuItem>
                    <MenuItem value="ones">Wszystko po 1 szt</MenuItem>
                  </TextField>
                  <FormControlLabel
                    control={
                      <Checkbox checked={firstWydawka} onChange={(e) => setFirstWydawka(e.target.checked)} />
                    }
                    label="Pierwsza wydawka (dolacz baze materialow)"
                  />
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
