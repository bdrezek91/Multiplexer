import {
  Alert,
  Box,
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
import { useQuery } from '@tanstack/react-query'
import { getSystemStatus } from '../api/system'

function formatMs(value: number | null) {
  if (value === null) return '-'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(1)} s`
}

function formatBackup(last: string | null, ageHours: number | null) {
  if (!last) return 'brak'
  const date = new Date(last).toLocaleString('pl-PL')
  return ageHours === null ? date : `${date} (${ageHours.toFixed(1)} h temu)`
}

function StateCard({
  title,
  ok,
  value,
}: {
  title: string
  ok: boolean
  value: string
}) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, minWidth: 185 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <Typography variant="subtitle2">{title}</Typography>
        <Chip size="small" color={ok ? 'success' : 'error'} label={ok ? 'OK' : 'BŁĄD'} />
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
        {value}
      </Typography>
    </Paper>
  )
}

export function SystemStatusPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ['systemStatus'],
    queryFn: getSystemStatus,
    refetchInterval: 10_000,
  })

  if (isLoading) {
    return <Typography>Ładowanie stanu systemu...</Typography>
  }

  if (error || !data) {
    return <Alert severity="error">Nie udało się pobrać stanu Multipleksera.</Alert>
  }

  const overallColor = data.overall === 'ok' ? 'success' : data.overall === 'warning' ? 'warning' : 'error'
  const overallLabel = data.overall === 'ok' ? 'System OK' : data.overall === 'warning' ? 'Ostrzeżenie' : 'Błąd systemu'

  return (
    <Box>
      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <Typography variant="h5">Stan systemu</Typography>
        <Chip color={overallColor} label={overallLabel} />
        <Typography variant="caption" color="text.secondary">
          aktualizacja: {new Date(data.generated_at).toLocaleTimeString('pl-PL')}
        </Typography>
      </Stack>

      {data.alerts.length > 0 ? (
        <Stack spacing={1} sx={{ mb: 2 }}>
          {data.alerts.map((alert) => (
            <Alert key={alert.code} severity={alert.severity}>
              {alert.message}
            </Alert>
          ))}
        </Stack>
      ) : (
        <Alert severity="success" sx={{ mb: 2 }}>
          Brak aktywnych alertów.
        </Alert>
      )}

      <Typography variant="subtitle1" sx={{ mb: 1 }}>Usługi i workery</Typography>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 3 }}>
        {Object.entries(data.services).map(([name, state]) => (
          <StateCard
            key={name}
            title={name}
            ok={state.ok}
            value={state.detail ?? 'działa prawidłowo'}
          />
        ))}
        {Object.entries(data.workers).map(([name, state]) => (
          <StateCard
            key={name}
            title={`Worker ${name}`}
            ok={state.online}
            value={state.node ?? 'brak odpowiedzi'}
          />
        ))}
      </Stack>

      <Typography variant="subtitle1" sx={{ mb: 1 }}>Kolejki i wydajność</Typography>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 3 }}>
        <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
          <Typography variant="h5">{data.queues.ocr?.length ?? '-'}</Typography>
          <Typography variant="body2" color="text.secondary">Kolejka OCR</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
          <Typography variant="h5">{data.queues.background?.length ?? '-'}</Typography>
          <Typography variant="body2" color="text.secondary">Kolejka background</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
          <Typography variant="h5">{formatMs(data.last_document_ms)}</Typography>
          <Typography variant="body2" color="text.secondary">Ostatnia wydawka</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
          <Typography variant="h5">{formatMs(data.avg_last10_ms)}</Typography>
          <Typography variant="body2" color="text.secondary">Średnia ostatnich 10</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
          <Typography variant="h5">{data.documents_error_24h}</Typography>
          <Typography variant="body2" color="text.secondary">Dokumenty error / 24 h</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
          <Typography variant="h5">{data.ai_failed_events_24h}</Typography>
          <Typography variant="body2" color="text.secondary">Błędy prób AI / 24 h</Typography>
        </Paper>
      </Stack>

      <Typography variant="subtitle1" sx={{ mb: 1 }}>AI i backup</Typography>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 3 }}>
        <StateCard
          title="Backup"
          ok={data.backup_ok}
          value={formatBackup(data.backup_last_success, data.backup_age_hours)}
        />
        <StateCard
          title="Jev"
          ok={data.jev_enabled && data.jev_mode === 'active'}
          value={`${data.jev_mode.toUpperCase()} • ${data.jev_model}`}
        />
      </Stack>

      {data.cooldowns.length > 0 && (
        <Paper variant="outlined" sx={{ p: 1.5, mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Aktywne cooldowny modeli</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {data.cooldowns.map((cooldown) => (
              <Chip
                key={cooldown.label}
                color="warning"
                variant="outlined"
                label={`${cooldown.label}: ${Math.ceil(cooldown.remaining_seconds / 60)} min`}
              />
            ))}
          </Stack>
        </Paper>
      )}

      <Typography variant="subtitle1" sx={{ mb: 1 }}>Ostatnie wydawki</Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Projekt</TableCell>
              <TableCell>Utworzono</TableCell>
              <TableCell align="right">Czas do wyniku</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.recent_documents.map((doc) => (
              <TableRow key={doc.document_id}>
                <TableCell>{doc.numer_projektu ?? '-'}</TableCell>
                <TableCell>{new Date(doc.created_at).toLocaleString('pl-PL')}</TableCell>
                <TableCell align="right">{formatMs(doc.duration_ms)}</TableCell>
              </TableRow>
            ))}
            {data.recent_documents.length === 0 && (
              <TableRow>
                <TableCell colSpan={3}>Brak danych telemetrycznych.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  )
}
