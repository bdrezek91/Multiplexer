import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { getDocument } from '../api/documents'
import { StatusChip } from '../components/StatusChip'
import { MatchQualityChip } from '../components/MatchQualityChip'
import { ApiError } from '../api/client'

export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

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
          </Paper>

          {document.status === 'done' && (
            <TableContainer component={Paper}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Rozpoznana nazwa</TableCell>
                    <TableCell>Ilosc wydana</TableCell>
                    <TableCell>Ilosc zuzyta</TableCell>
                    <TableCell>Dopasowany kod</TableCell>
                    <TableCell>Jakosc dopasowania</TableCell>
                    <TableCell>Uwagi</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {document.items.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6}>AI nie wykrylo zadnych pozycji na skanie</TableCell>
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
          )}
        </>
      )}
    </Box>
  )
}
