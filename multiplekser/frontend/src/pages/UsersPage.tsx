import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
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
  Tooltip,
  Typography,
} from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import AddIcon from '@mui/icons-material/Add'
import KeyIcon from '@mui/icons-material/VpnKey'
import DeleteIcon from '@mui/icons-material/Delete'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteUser, listUsers } from '../api/users'
import { getDocumentStats } from '../api/documents'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { UserFormDialog } from './UserFormDialog'
import { ResetPasswordDialog } from './ResetPasswordDialog'
import type { CurrentUser, DailyDocumentStats } from '../types'

// Statystyki wydajnosci (2026-09-21, na zyczenie uzytkownika) - ile dokumentow przerobil kazdy
// uzytkownik, zestawione z szacowanym zaoszczedzonym czasem/pieniedzmi wzgledem recznego
// wprowadzania wydawki (backend: GET /documents/stats/summary, zalozenia tam opisane).
function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Paper variant="outlined" sx={{ px: 2, py: 1.5, minWidth: 180 }}>
      <Typography variant="h5">{value}</Typography>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
    </Paper>
  )
}

type ChartMetric = 'documents' | 'hours' | 'money'

const USER_COLORS = ['primary.main', 'secondary.main', 'success.main', 'warning.main']

function displayUserName(email: string): string {
  if (email.startsWith('marzena.')) return 'Marzena'
  if (email.startsWith('bdrezek91@')) return 'Bartek'
  if (email.startsWith('paula.')) return 'Paula'
  if (email.startsWith('krzysztof.')) return 'Krzysztof'
  return email.split('@')[0]
}

function metricValue(
  row: { dokumenty: number; minuty_zaoszczedzone: number; pieniadze_zaoszczedzone: number },
  metric: ChartMetric,
): number {
  if (metric === 'hours') return row.minuty_zaoszczedzone / 60
  if (metric === 'money') return row.pieniadze_zaoszczedzone
  return row.dokumenty
}

function formatMetric(value: number, metric: ChartMetric): string {
  if (metric === 'hours') return value.toFixed(1) + ' h'
  if (metric === 'money') return value.toFixed(2) + ' zł'
  return String(Math.round(value))
}

function DailyStatsChart({ daily }: { daily: DailyDocumentStats[] }) {
  const [metric, setMetric] = useState<ChartMetric>('documents')

  if (daily.length === 0) return null

  const emails = Array.from(new Set(daily.flatMap((day) => day.per_user.map((row) => row.email))))
  const colorByEmail = new Map(emails.map((email, index) => [email, USER_COLORS[index % USER_COLORS.length]]))
  const maxValue = Math.max(...daily.map((day) => metricValue(day, metric)), 1)

  return (
    <Box sx={{ mb: 3 }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        gap={1}
        sx={{ mb: 1.5 }}
      >
        <Typography variant="subtitle2">Przebieg dzienny</Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={metric}
          onChange={(_, value: ChartMetric | null) => value && setMetric(value)}
        >
          <ToggleButton value="documents">Wydawki</ToggleButton>
          <ToggleButton value="hours">Godziny</ToggleButton>
          <ToggleButton value="money">Oszczędności</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
        {emails.map((email) => (
          <Stack key={email} direction="row" spacing={0.75} alignItems="center">
            <Box sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: colorByEmail.get(email) }} />
            <Typography variant="caption" color="text.secondary">
              {displayUserName(email)}
            </Typography>
          </Stack>
        ))}
      </Stack>

      <Box sx={{ overflowX: 'auto', pb: 1 }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 0.75,
            minWidth: Math.max(860, daily.length * 42),
            height: 245,
            px: 1,
            borderBottom: 1,
            borderColor: 'divider',
          }}
        >
          {daily.map((day) => {
            const total = metricValue(day, metric)
            const barHeight = Math.max(8, (total / maxValue) * 185)
            const dateLabel = new Date(day.data + 'T00:00:00').toLocaleDateString('pl-PL', {
              day: '2-digit',
              month: '2-digit',
            })
            const fullDate = new Date(day.data + 'T00:00:00').toLocaleDateString('pl-PL', {
              weekday: 'long',
              day: '2-digit',
              month: '2-digit',
              year: 'numeric',
            })

            return (
              <Box
                key={day.data}
                sx={{ width: 34, flex: '0 0 34px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}
              >
                <Tooltip
                  arrow
                  placement="top"
                  title={
                    <Box sx={{ minWidth: 180 }}>
                      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                        {fullDate}
                      </Typography>
                      <Typography variant="body2" sx={{ mb: 0.75 }}>
                        Razem: {formatMetric(total, metric)}
                      </Typography>
                      {day.per_user.map((row) => (
                        <Typography key={row.email} variant="caption" display="block">
                          {displayUserName(row.email)}: {formatMetric(metricValue(row, metric), metric)}
                        </Typography>
                      ))}
                    </Box>
                  }
                >
                  <Box
                    sx={{
                      width: 28,
                      height: barHeight,
                      minHeight: 8,
                      display: 'flex',
                      flexDirection: 'column-reverse',
                      overflow: 'hidden',
                      borderRadius: '5px 5px 2px 2px',
                      cursor: 'default',
                      boxShadow: 1,
                      transition: 'height 180ms ease',
                    }}
                  >
                    {day.per_user.map((row) => {
                      const value = metricValue(row, metric)
                      const share = total > 0 ? (value / total) * 100 : 0
                      return (
                        <Box
                          key={row.email}
                          sx={{
                            height: share + '%',
                            minHeight: value > 0 ? 2 : 0,
                            bgcolor: colorByEmail.get(row.email),
                          }}
                        />
                      )
                    })}
                  </Box>
                </Tooltip>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mt: 0.75, fontSize: '0.64rem', transform: 'rotate(-45deg)', transformOrigin: 'top center' }}
                >
                  {dateLabel}
                </Typography>
              </Box>
            )
          })}
        </Box>
      </Box>
    </Box>
  )
}

function DocumentStatsPanel() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['documentStats'],
    queryFn: getDocumentStats,
  })

  if (isLoading) return null

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 3 }}>
        {error instanceof ApiError ? error.detail : 'Nie udało się pobrać statystyk'}
      </Alert>
    )
  }
  if (!stats) return null

  const godzinyRazem = (stats.razem_minuty_zaoszczedzone / 60).toFixed(1)

  return (
    <Paper sx={{ p: 2, mb: 3 }}>
      <Typography variant="subtitle1" gutterBottom>
        Statystyki wydajności od 08.09.2026
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Statystyki szacunkowe. Przy założeniu ok. {stats.minuty_na_dokument} min na ręczne
        wprowadzenie jednej wydawki (z przerwami) i {stats.stawka_pln_za_h.toFixed(2)} zł/h
        kosztu pracodawcy (brutto ze składkami).
      </Typography>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <StatCard label="Wydawki łącznie" value={String(stats.razem_dokumenty)} />
        <StatCard label="Zaoszczędzony czas" value={`${godzinyRazem} h`} />
        <StatCard
          label="Zaoszczędzone pieniądze"
          value={`${stats.razem_pieniadze_zaoszczedzone.toFixed(2)} zł`}
        />
      </Stack>

      <DailyStatsChart daily={stats.daily} />

      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Użytkownik</TableCell>
              <TableCell align="right">Dokumenty</TableCell>
              <TableCell align="right">Czas zaoszczędzony</TableCell>
              <TableCell align="right">Pieniądze zaoszczędzone</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {stats.per_user.length === 0 && (
              <TableRow>
                <TableCell colSpan={4}>Brak jeszcze przerobionych dokumentów</TableCell>
              </TableRow>
            )}
            {stats.per_user.map((row) => (
              <TableRow key={row.user_id} hover>
                <TableCell>{row.email}</TableCell>
                <TableCell align="right">{row.dokumenty}</TableCell>
                <TableCell align="right">{(row.minuty_zaoszczedzone / 60).toFixed(1)} h</TableCell>
                <TableCell align="right">{row.pieniadze_zaoszczedzone.toFixed(2)} zł</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  )
}

export function UsersPage() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()

  const [formOpen, setFormOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<CurrentUser | null>(null)
  const [resetTarget, setResetTarget] = useState<CurrentUser | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const { data: users, isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: listUsers,
  })

  const openCreateDialog = () => {
    setEditingUser(null)
    setFormOpen(true)
  }

  const openEditDialog = (u: CurrentUser) => {
    setEditingUser(u)
    setFormOpen(true)
  }

  const deleteMutation = useMutation({
    mutationFn: (u: CurrentUser) => deleteUser(u.id),
    onSuccess: () => {
      setDeleteError(null)
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      void queryClient.invalidateQueries({ queryKey: ['documentStats'] })
    },
    onError: (err) => {
      setDeleteError(err instanceof ApiError ? err.detail : 'Nie udało się usunąć użytkownika')
    },
  })

  const handleDelete = (u: CurrentUser) => {
    if (currentUser?.id === u.id) return
    setDeleteError(null)
    const confirmed = window.confirm(
      'Usunąć użytkownika "' + u.email + '"? Tej operacji nie można cofnąć. ' +
      'Jeśli konto ma historię operacyjną, system odmówi usunięcia i pozostawi możliwość dezaktywacji.',
    )
    if (confirmed) deleteMutation.mutate(u)
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h5">Użytkownicy</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openCreateDialog}>
          Nowy użytkownik
        </Button>
      </Stack>

      <DocumentStatsPanel />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error instanceof ApiError ? error.detail : 'Nie udało się pobrać listy użytkowników'}
        </Alert>
      )}
      {deleteError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {deleteError}
        </Alert>
      )}

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Email</TableCell>
              <TableCell>Rola</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Akcje</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={4}>Ładowanie...</TableCell>
              </TableRow>
            )}
            {!isLoading && (users ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={4}>Brak użytkowników</TableCell>
              </TableRow>
            )}
            {(users ?? []).map((u) => (
              <TableRow key={u.id} hover>
                <TableCell>
                  {u.email}
                  {currentUser?.id === u.id && <Chip size="small" label="Ty" sx={{ ml: 1 }} />}
                </TableCell>
                <TableCell>
                  <Chip size="small" label={u.rola} color={u.rola === 'admin' ? 'primary' : 'default'} />
                </TableCell>
                <TableCell>
                  <Chip size="small" label={u.active ? 'aktywny' : 'nieaktywny'} color={u.active ? 'success' : 'default'} />
                </TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={() => openEditDialog(u)} aria-label={`Edytuj ${u.email}`}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton size="small" onClick={() => setResetTarget(u)} aria-label={'Resetuj hasło ' + u.email}>
                    <KeyIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    onClick={() => handleDelete(u)}
                    aria-label={'Usuń ' + u.email}
                    title={currentUser?.id === u.id ? 'Nie można usunąć własnego konta' : 'Usuń użytkownika'}
                    disabled={currentUser?.id === u.id || deleteMutation.isPending}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {formOpen && (
        <UserFormDialog
          open={formOpen}
          onClose={() => setFormOpen(false)}
          user={editingUser}
          isSelf={editingUser !== null && editingUser.id === currentUser?.id}
        />
      )}
      {resetTarget && (
        <ResetPasswordDialog open={Boolean(resetTarget)} onClose={() => setResetTarget(null)} user={resetTarget} />
      )}
    </Box>
  )
}
