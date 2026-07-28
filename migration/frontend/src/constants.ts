// Jedyne dwa magazyny z realnym znaczeniem biznesowym w calym systemie - patrz
// backend/app/modules/matcher/core.py, magazyn_key() (R5, podstawienie wariantu magazynowego).
// System nigdy nie mial osobnej encji Warehouse (magazyn to zawsze string) - ta lista jest
// swiadomie zaszyta tu, w jedynym miejscu, zamiast pozwalac na dowolny tekst.
//
// `value` to DOKLADNA nazwa magazynu jakiej oczekuje Optima - trafia bez zmian do ostatniej
// kolumny generowanego pliku TXT (patrz backend generate_output()) i jest tym, co faktycznie
// zapisywane jest w bazie (Document.magazyn / UserModel.magazyny_dostepne). `label` to tylko
// przyjazna etykieta na przycisku w UI - magazyn_key() w backendzie dopasowuje po podciagu
// ("zabrze"/"czekan"), wiec dziala niezaleznie od dokladnego brzmienia `value`.
export interface KnownMagazyn {
  value: string
  label: string
}

export const KNOWN_MAGAZYNY: KnownMagazyn[] = [
  { value: 'Mag m-y Zabrze', label: 'Magazyn Zabrze' },
  { value: 'MAGAZYN Czekanów', label: 'Magazyn Czekanów' },
]

export function magazynLabel(value: string): string {
  return KNOWN_MAGAZYNY.find((m) => m.value === value)?.label ?? value
}
