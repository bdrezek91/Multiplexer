import { Chip, Tooltip } from '@mui/material'
import type { Dzial } from '../types'

const LABELS: Record<Dzial, string> = {
  elektryka: 'Elektryka',
  hydraulika: 'Hydraulika',
}

const COLORS: Record<Dzial, 'primary' | 'secondary'> = {
  elektryka: 'primary',
  hydraulika: 'secondary',
}

// Dzial jest wykrywany automatycznie przez klasyfikacje OCR (Krok Hydraulika-3) - brak
// recznego wyboru w UI, wiec `null` oznacza "jeszcze nie wiadomo" (dokument w kolejce/w
// trakcie przetwarzania albo przerwany bledem przed etapem klasyfikacji), nie blad.
export function DzialChip({ dzial, confidence }: { dzial: Dzial | null; confidence?: number | null }) {
  if (!dzial) {
    return <Chip size="small" label="–" variant="outlined" />
  }
  const label = LABELS[dzial] ?? dzial
  const chip = <Chip size="small" label={label} color={COLORS[dzial] ?? 'default'} />
  if (confidence == null) return chip
  return <Tooltip title={`Wykryto automatycznie, pewność ${confidence.toFixed(0)}%`}>{chip}</Tooltip>
}
