"""pickQty() z monolitu - domyslna ilosc do przedstawienia uzytkownikowi do weryfikacji/edycji
przed generowaniem. Monolit mial przelacznik 'wydana'/'zuzyta'/'razem' (domyslnie 'razem') do
wyboru, ktora kolumna wypelnia edytowalne pole `.qty-input`; w tym etapie wspieramy tylko
domyslne 'razem' (zuzyta jesli podana, inaczej wydana) - patrz RAPORT_ETAP_9.md, uzytkownik
nadal moze recznie nadpisac ilosc_finalna przez PATCH przed wygenerowaniem."""
from __future__ import annotations

from typing import Optional


def pick_qty_razem(ilosc_wydana: Optional[float], ilosc_zuzyta: Optional[float]) -> Optional[float]:
    return ilosc_zuzyta if ilosc_zuzyta is not None else ilosc_wydana
