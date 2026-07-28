import { Chip } from '@mui/material'
import type { DocumentStatus } from '../types'

const LABELS: Record<DocumentStatus, string> = {
  queued: 'W kolejce',
  processing: 'Przetwarzanie',
  done: 'Gotowe',
  error: 'Błąd',
}

const COLORS: Record<DocumentStatus, 'default' | 'info' | 'success' | 'error'> = {
  queued: 'default',
  processing: 'info',
  done: 'success',
  error: 'error',
}

export function StatusChip({ status }: { status: DocumentStatus }) {
  return <Chip size="small" label={LABELS[status]} color={COLORS[status]} />
}
