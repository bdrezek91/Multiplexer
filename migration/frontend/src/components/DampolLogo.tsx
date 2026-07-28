import { Box, Typography } from '@mui/material'
import { DAMPOL_GOLD } from '../theme'

// Odtworzone tekstowo ze zrzutu ekranu strony dampol-investment.com (brak dostepu sieciowego z tej
// sesji do pobrania oryginalnego pliku logo - patrz rozmowa) - "DAMPOL" pogrubione, pod spodem
// "INVESTMENT" mniejsze, jasniejsze, z szerokimi odstepami miedzy literami, jak w oryginale.
export function DampolLogo({ fontSize = 22 }: { fontSize?: number }) {
  return (
    <Box lineHeight={1}>
      <Typography
        component="span"
        sx={{ fontSize, fontWeight: 800, letterSpacing: '0.04em', color: DAMPOL_GOLD, display: 'block' }}
      >
        DAMPOL
      </Typography>
      <Typography
        component="span"
        sx={{
          fontSize: fontSize * 0.32,
          fontWeight: 500,
          letterSpacing: '0.35em',
          color: DAMPOL_GOLD,
          opacity: 0.85,
          display: 'block',
        }}
      >
        INVESTMENT
      </Typography>
    </Box>
  )
}
