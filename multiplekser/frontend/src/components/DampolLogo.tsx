import { Box } from '@mui/material'
import { DAMPOL_GOLD } from '../theme'

// Odtworzone jako SVG na podstawie zrzutu ekranu logo przeslanego przez uzytkownika (brak dostepu
// sieciowego z tej sesji do pobrania oryginalnego pliku - patrz rozmowa): "DAMPOL" konturowe
// (puste w srodku, tylko obrys), pod spodem pelne "INVESTMENT" z szerokimi odstepami miedzy
// literami - tak jak w oryginale. SVG (nie zwykly tekst z -webkit-text-stroke) dla identycznego,
// ostrego wygladu na kazdej przegladarce niezaleznie od wsparcia dla obrysu tekstu w CSS.
export function DampolLogo({ height = 34 }: { height?: number }) {
  return (
    <Box
      component="svg"
      viewBox="0 0 620 172"
      role="img"
      aria-label="Dampol Investment"
      sx={{ height, width: 'auto', display: 'block' }}
    >
      <text
        x="310"
        y="118"
        textAnchor="middle"
        fontFamily="Arial, Helvetica, sans-serif"
        fontWeight={700}
        fontSize={122}
        letterSpacing={1}
        fill="none"
        stroke={DAMPOL_GOLD}
        strokeWidth={3.5}
      >
        DAMPOL
      </text>
      <text
        x="317"
        y="160"
        textAnchor="middle"
        fontFamily="Arial, Helvetica, sans-serif"
        fontWeight={500}
        fontSize={25}
        letterSpacing={14}
        fill={DAMPOL_GOLD}
      >
        INVESTMENT
      </text>
    </Box>
  )
}
