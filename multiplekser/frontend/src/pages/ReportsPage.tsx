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
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { listDocumentReports, resolveDocumentReport } from '../api/documents'
import { ApiError } from '../api/client'
import type { DocumentReportStatus } from '../types'

export function ReportsPage() {
  const [statusFilter, setStatusFilter] = useState<DocumentReportStatus | 'all'>('open')
  const queryClient = useQueryClient()

  const { data: reports, isLoading, error } = useQuery({
    queryKey: ['document-reports', statusFilter],
    queryFn: () => listDocumentReports(statusFilter === 'all' ? undefined : statusFilter),
  })

  const resolveMutation = useMutation({
    mutationFn: (reportId: string) => resolveDocumentReport(reportId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['document-reports'] }),
  })

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2} flexWrap="wrap" gap={2}>
        <Typography variant="h5">Zgłoszenia problemów</Typography>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={statusFilter}
          onChange={(_, next: DocumentReportStatus | 'all' | null) => next && setStatusFilter(next)}
        >
          <ToggleButton value="open">Otwarte</ToggleButton>
          <ToggleButton value="resolved">Rozwiązane</ToggleButton>
          <ToggleButton value="all">Wszystkie</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error instanceof ApiError ? error.detail : 'Nie udało się pobrać zgłoszeń'}
        </Alert>
      )}

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Dokument</TableCell>
              <TableCell>Zgłoszone przez</TableCell>
              <TableCell>Opis</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Data zgłoszenia</TableCell>
              <TableCell align="right">Akcje</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={6}>Ładowanie...</TableCell>
              </TableRow>
            )}
            {!isLoading && (reports ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>Brak zgłoszeń</TableCell>
              </TableRow>
            )}
            {(reports ?? []).map((report) => (
              <TableRow key={report.id} hover>
                <TableCell>
                  <RouterLink to={`/documents/${report.document_id}`}>
                    {report.document_original_filename}
                  </RouterLink>
                </TableCell>
                <TableCell>{report.reported_by_email}</TableCell>
                <TableCell sx={{ maxWidth: 400, whiteSpace: 'pre-wrap' }}>{report.opis}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={report.status === 'open' ? 'otwarte' : 'rozwiązane'}
                    color={report.status === 'open' ? 'warning' : 'success'}
                  />
                </TableCell>
                <TableCell>{new Date(report.created_at).toLocaleString('pl-PL')}</TableCell>
                <TableCell align="right">
                  {report.status === 'open' && (
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={resolveMutation.isPending}
                      onClick={() => resolveMutation.mutate(report.id)}
                    >
                      Oznacz jako rozwiązane
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  )
}
