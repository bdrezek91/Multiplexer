import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

/**
 * Never hard-code release numbers in frontend components.
 * Production backend serves the root VERSION file at /api/version.
 */
export function AppVersion() {
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    apiRequest<{ version: string }>('/version', { skipAuth: true })
      .then((result) => {
        if (!active) return
        if (!result.version || result.version === 'unknown') return
        setVersion(result.version)
        document.title = `Multiplekser v${result.version}`
      })
      .catch(() => {
        // Do not claim an outdated version when backend is unavailable.
      })
    return () => { active = false }
  }, [])

  return <>Multiplekser{version ? ` v${version}` : ''}</>
}
