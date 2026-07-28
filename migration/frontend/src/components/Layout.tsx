import { AppBar, Box, Button, Container, Toolbar, Typography } from '@mui/material'
import type { ReactNode } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <Box display="flex" flexDirection="column" minHeight="100vh">
      <AppBar position="static">
        <Toolbar sx={{ gap: 2 }}>
          <Typography variant="h6" component="div" sx={{ flexGrow: 0, mr: 2 }}>
            Multiplekser Elektryka
          </Typography>
          <Button color="inherit" component={RouterLink} to="/documents">
            Dokumenty
          </Button>
          <Button color="inherit" component={RouterLink} to="/products">
            Katalog produktów
          </Button>
          {user?.rola === 'admin' && (
            <Button color="inherit" component={RouterLink} to="/users">
              Użytkownicy
            </Button>
          )}
          <Box flexGrow={1} />
          {user && (
            <>
              <Typography variant="body2" sx={{ mr: 2 }}>
                {user.email} ({user.rola})
              </Typography>
              <Button color="inherit" onClick={handleLogout}>
                Wyloguj
              </Button>
            </>
          )}
        </Toolbar>
      </AppBar>
      <Container component="main" sx={{ flexGrow: 1, py: 3 }}>
        {children}
      </Container>
    </Box>
  )
}
