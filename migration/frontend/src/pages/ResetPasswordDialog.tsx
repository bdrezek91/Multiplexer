import { useState, type FormEvent } from 'react'
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField } from '@mui/material'
import { useMutation } from '@tanstack/react-query'
import { resetPassword } from '../api/users'
import { ApiError } from '../api/client'
import type { CurrentUser } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  user: CurrentUser
}

export function ResetPasswordDialog({ open, onClose, user }: Props) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const mutation = useMutation({
    mutationFn: () => resetPassword(user.id, password),
    onSuccess: () => setDone(true),
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Nie udalo sie zresetowac hasla'),
  })

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    mutation.mutate()
  }

  const handleClose = () => {
    setPassword('')
    setError(null)
    setDone(false)
    onClose()
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle>Resetuj haslo: {user.email}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            {done ? (
              <Alert severity="success">Haslo zostalo zmienione.</Alert>
            ) : (
              <TextField
                label="Nowe haslo"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoFocus
                helperText="Minimum 8 znakow - przekaz je uzytkownikowi bezpiecznym kanalem"
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>{done ? 'Zamknij' : 'Anuluj'}</Button>
          {!done && (
            <Button type="submit" variant="contained" disabled={mutation.isPending}>
              {mutation.isPending ? 'Resetowanie...' : 'Resetuj haslo'}
            </Button>
          )}
        </DialogActions>
      </form>
    </Dialog>
  )
}
