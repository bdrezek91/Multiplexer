import { useState, type FormEvent } from 'react'
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createUser, updateUser } from '../api/users'
import { ApiError } from '../api/client'
import type { CurrentUser, Rola } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  user: CurrentUser | null // null = tworzenie nowego uzytkownika
  isSelf: boolean // edytowany uzytkownik to zalogowany admin - blokada dezaktywacji/degradacji (patrz backend)
}

export function UserFormDialog({ open, onClose, user, isSelf }: Props) {
  const queryClient = useQueryClient()
  const isEditing = user !== null

  const [email, setEmail] = useState(user?.email ?? '')
  const [password, setPassword] = useState('')
  const [rola, setRola] = useState<Rola>(user?.rola ?? 'elektryk')
  const [magazynyText, setMagazynyText] = useState(user?.magazyny_dostepne.join(', ') ?? '')
  const [active, setActive] = useState(user?.active ?? true)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      const magazyny_dostepne = magazynyText
        .split(',')
        .map((m) => m.trim())
        .filter(Boolean)
      if (isEditing) {
        return updateUser(user.id, { email, rola, magazyny_dostepne, active })
      }
      return createUser({ email, password, rola, magazyny_dostepne })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : 'Nie udalo sie zapisac uzytkownika')
    },
  })

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    mutation.mutate()
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle>{isEditing ? `Edytuj uzytkownika: ${user.email}` : 'Nowy uzytkownik'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            {isSelf && (
              <Alert severity="info">
                To Twoje wlasne konto - nie mozesz go tu zdezaktywowac ani zdegradowac z roli admin.
              </Alert>
            )}
            <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            {!isEditing && (
              <TextField
                label="Haslo"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                helperText="Minimum 8 znakow"
              />
            )}
            <TextField
              select
              label="Rola"
              value={rola}
              onChange={(e) => setRola(e.target.value as Rola)}
              disabled={isSelf}
            >
              <MenuItem value="elektryk">elektryk</MenuItem>
              <MenuItem value="admin">admin</MenuItem>
            </TextField>
            <TextField
              label="Magazyny dostepne (oddzielone przecinkami)"
              value={magazynyText}
              onChange={(e) => setMagazynyText(e.target.value)}
              helperText="Ignorowane dla roli admin - admin ma dostep do kazdego magazynu"
            />
            {isEditing && (
              <FormControlLabel
                control={
                  <Checkbox checked={active} onChange={(e) => setActive(e.target.checked)} disabled={isSelf} />
                }
                label="Aktywny"
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Anuluj</Button>
          <Button type="submit" variant="contained" disabled={mutation.isPending}>
            {mutation.isPending ? 'Zapisywanie...' : 'Zapisz'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}
