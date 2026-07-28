import { useState, type FormEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  FormHelperText,
  MenuItem,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createUser, updateUser } from '../api/users'
import { ApiError } from '../api/client'
import { KNOWN_MAGAZYNY } from '../constants'
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
  const [magazynyDostepne, setMagazynyDostepne] = useState<string[]>(user?.magazyny_dostepne ?? [])
  const [active, setActive] = useState(user?.active ?? true)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      if (isEditing) {
        return updateUser(user.id, { email, rola, magazyny_dostepne: magazynyDostepne, active })
      }
      return createUser({ email, password, rola, magazyny_dostepne: magazynyDostepne })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : 'Nie udało się zapisać użytkownika')
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
        <DialogTitle>{isEditing ? `Edytuj użytkownika: ${user.email}` : 'Nowy użytkownik'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            {isSelf && (
              <Alert severity="info">
                To Twoje własne konto - nie możesz go tu zdezaktywować ani zdegradować z roli admin.
              </Alert>
            )}
            <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            {!isEditing && (
              <TextField
                label="Hasło"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                helperText="Minimum 8 znaków"
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
            <Box>
              <Typography variant="body2" color={rola === 'admin' ? 'text.disabled' : 'text.secondary'}>
                Magazyny dostępne
              </Typography>
              <ToggleButtonGroup
                value={magazynyDostepne}
                onChange={(_, next: string[]) => setMagazynyDostepne(next)}
                disabled={rola === 'admin'}
                size="small"
                sx={{ mt: 0.5 }}
              >
                {KNOWN_MAGAZYNY.map((m) => (
                  <ToggleButton key={m.value} value={m.value}>
                    {m.label}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
              <FormHelperText>Ignorowane dla roli admin - admin ma dostęp do każdego magazynu</FormHelperText>
            </Box>
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
