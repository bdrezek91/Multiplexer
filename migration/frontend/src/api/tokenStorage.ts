// Przechowywanie tokenow JWT (Etap 8). localStorage - prostota MVP; swiadomy kompromis
// bezpieczenstwa (podatnosc na XSS w porownaniu do httpOnly cookie) odnotowany w
// docs/RAPORT_ETAP_8.md jako ryzyko do rozwazenia przy twardnieniu bezpieczenstwa.

const ACCESS_KEY = 'multiplekser.access_token'
const REFRESH_KEY = 'multiplekser.refresh_token'

export const tokenStorage = {
  getAccessToken: () => localStorage.getItem(ACCESS_KEY),
  getRefreshToken: () => localStorage.getItem(REFRESH_KEY),
  setTokens: (accessToken: string, refreshToken: string) => {
    localStorage.setItem(ACCESS_KEY, accessToken)
    localStorage.setItem(REFRESH_KEY, refreshToken)
  },
  setAccessToken: (accessToken: string) => {
    localStorage.setItem(ACCESS_KEY, accessToken)
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}
