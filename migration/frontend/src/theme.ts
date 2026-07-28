import { createTheme } from '@mui/material/styles'

// Szata graficzna dopasowana do strony dampol-investment.com (na prosbe uzytkownika, 2026-07-28):
// ciemne, niemal czarne tlo + zloty akcent, pogrubione naglowki z odstepami miedzy literami.
// Nazwa marki i kolory zostaly odtworzone ze zrzutu ekranu strony (brak dostepu sieciowego z tej
// sesji do samej strony - patrz rozmowa) - jesli klient dostarczy oficjalna ksiazke znaku/hex,
// latwo podmienic wartosci ponizej, cala reszta UI korzysta z tych zmiennych przez theme.palette.
export const DAMPOL_GOLD = '#C9A227'
export const DAMPOL_GOLD_LIGHT = '#E0C158'
export const DAMPOL_BG_DEFAULT = '#121212'
export const DAMPOL_BG_PAPER = '#1a1a1a'
export const DAMPOL_BG_HEADER = '#0d0d0d'

export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: DAMPOL_GOLD, light: DAMPOL_GOLD_LIGHT, contrastText: '#0d0d0d' },
    secondary: { main: DAMPOL_GOLD_LIGHT },
    background: { default: DAMPOL_BG_DEFAULT, paper: DAMPOL_BG_PAPER },
  },
  typography: {
    h5: { fontWeight: 700, letterSpacing: '0.03em' },
    h6: { fontWeight: 700, letterSpacing: '0.06em' },
    button: { fontWeight: 600, letterSpacing: '0.04em' },
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: { backgroundColor: DAMPOL_BG_HEADER, borderBottom: `1px solid ${DAMPOL_GOLD}` },
      },
    },
    MuiButton: {
      styleOverrides: {
        containedPrimary: { color: '#0d0d0d' },
      },
    },
  },
})
