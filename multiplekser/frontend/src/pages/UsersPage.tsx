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
import type { CurrentUser } from '../types'

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
