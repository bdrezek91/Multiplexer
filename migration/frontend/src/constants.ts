// Jedyne dwie nazwy magazynow z realnym znaczeniem biznesowym w calym systemie - patrz
// backend/app/modules/matcher/core.py, magazyn_key() (R5, podstawienie wariantu magazynowego).
// System nigdy nie mial osobnej encji Warehouse (magazyn to zawsze string) - ta lista jest
// swiadomie zaszyta tu, w jedynym miejscu, zamiast pozwalac na dowolny tekst.
export const KNOWN_MAGAZYNY = ['Czekanów', 'Zabrze'] as const
