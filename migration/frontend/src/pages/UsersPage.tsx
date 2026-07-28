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
import { useQuery } from '@tanstack/react-query'
import { listUsers } from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { UserFormDialog } from './UserFormDialog'
import { ResetPasswordDialog } from './ResetPasswordDialog'
import type { CurrentUser } from '../types'

export function UsersPage() {
  const { user: currentUser } = useAuth()

  const [formOpen, setFormOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<CurrentUser | null>(null)
  const [resetTarget, setResetTarget] = useState<CurrentUser | null>(null)

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

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h5">Uzytkownicy</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openCreateDialog}>
          Nowy uzytkownik
        </Button>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error instanceof ApiError ? error.detail : 'Nie udalo sie pobrac listy uzytkownikow'}
        </Alert>
      )}

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Email</TableCell>
              <TableCell>Rola</TableCell>
              <TableCell>Magazyny dostepne</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Akcje</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5}>Ladowanie...</TableCell>
              </TableRow>
            )}
            {!isLoading && (users ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>Brak uzytkownikow</TableCell>
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
                <TableCell>{u.rola === 'admin' ? 'wszystkie' : u.magazyny_dostepne.join(', ') || '-'}</TableCell>
                <TableCell>
                  <Chip size="small" label={u.active ? 'aktywny' : 'nieaktywny'} color={u.active ? 'success' : 'default'} />
                </TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={() => openEditDialog(u)} aria-label={`Edytuj ${u.email}`}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton size="small" onClick={() => setResetTarget(u)} aria-label={`Resetuj haslo ${u.email}`}>
                    <KeyIcon fontSize="small" />
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
