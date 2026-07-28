import { AppBar, Box, Button, Container, Toolbar, Typography } from '@mui/material'
import type { ReactNode } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { DampolLogo } from './DampolLogo'

const navButtonSx = {
  color: 'grey.100',
  '&:hover': { color: 'primary.main', backgroundColor: 'transparent' },
}

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <Box display="flex" flexDirection="column" minHeight="100vh">
      <AppBar position="static" elevation={0}>
        <Toolbar sx={{ gap: 2 }}>
          <Box sx={{ mr: 3 }}>
            <DampolLogo />
          </Box>
          <Typography variant="body2" component="div" sx={{ color: 'grey.500', flexGrow: 0, mr: 2 }}>
            Multiplekser v1.0.0
          </Typography>
          <Button sx={navButtonSx} component={RouterLink} to="/documents">
            Dokumenty
          </Button>
          <Button sx={navButtonSx} component={RouterLink} to="/products">
            Katalog produktów
          </Button>
          {user?.rola === 'admin' && (
            <Button sx={navButtonSx} component={RouterLink} to="/users">
              Użytkownicy
            </Button>
          )}
          <Box flexGrow={1} />
          {user && (
            <>
              <Typography variant="body2" sx={{ mr: 2, color: 'grey.400' }}>
                {user.email} ({user.rola})
              </Typography>
              <Button variant="outlined" color="primary" onClick={handleLogout}>
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
