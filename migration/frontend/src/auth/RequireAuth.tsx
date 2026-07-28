import { CircularProgress, Box } from '@mui/material'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
        <CircularProgress />
      </Box>
    )
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  if (user && user.rola !== 'admin') {
    return <Navigate to="/" replace />
  }
  return <RequireAuth>{children}</RequireAuth>
}
