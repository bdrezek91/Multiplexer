import { Chip } from '@mui/material'

const LABELS: Record<string, string> = {
  ok: 'OK',
  warn: 'Do sprawdzenia',
  bad: 'Brak dopasowania',
  excluded: 'Wykluczone',
}

const COLORS: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  ok: 'success',
  warn: 'warning',
  bad: 'error',
  excluded: 'default',
}

export function MatchQualityChip({ quality }: { quality: string }) {
  return <Chip size="small" label={LABELS[quality] ?? quality} color={COLORS[quality] ?? 'default'} />
}
