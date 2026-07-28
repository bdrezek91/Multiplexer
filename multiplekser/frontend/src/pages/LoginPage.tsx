import { useState, type FormEvent } from 'react'
import { Alert, Box, Button, Paper, TextField, Typography } from '@mui/material'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { DampolLogo } from '../components/DampolLogo'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      // Zawsze na /documents (nie "wroc tam gdzie bylem") - swiadome uproszczenie: probowanie
      // odtworzenia poprzedniej lokalizacji przez location.state.from kolidowalo z reaktywnym
      // przekierowaniem RequireAuth przy wylogowaniu (wyscig o to, czyj wpis historii wygra),
      // co po wylogowaniu i zalogowaniu SIE INNEGO uzytkownika potrafilo probowac otworzyc
      // cudzy, niedostepny dla niego dokument. Prostota > ta konkretna wygoda UX.
      navigate('/documents', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Nie udało się zalogować')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh" bgcolor="background.default">
      <Paper sx={{ p: 4, width: 360, border: 1, borderColor: 'divider' }} component="form" onSubmit={handleSubmit}>
        <Box display="flex" flexDirection="column" alignItems="center" mb={2} textAlign="center">
          <DampolLogo height={48} />
          <Typography variant="h5" sx={{ mt: 2 }}>
            Multiplekser v1.0.0
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Zaloguj się, aby kontynuować
          </Typography>
        </Box>
        {error && (
          <Alert severity="error" sx={{ my: 2 }}>
            {error}
          </Alert>
        )}
        <TextField
          label="Email"
          type="email"
          name="email"
          autoComplete="username"
          fullWidth
          margin="normal"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />
        <TextField
          label="Hasło"
          type="password"
          name="password"
          autoComplete="current-password"
          fullWidth
          margin="normal"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" variant="contained" fullWidth sx={{ mt: 2 }} disabled={submitting}>
          {submitting ? 'Logowanie...' : 'Zaloguj'}
        </Button>
      </Paper>
    </Box>
  )
}
