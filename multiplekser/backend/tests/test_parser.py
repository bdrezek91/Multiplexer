"""Testy modulu Parser - walidacja 1:1 zgodnosci z coreAndAttrs()/detectPhase() z monolitu
(patrz index.html, linie ok. 145-315). Kazdy przypadek tu to gap znaleziony podczas walidacji
zamowionej przez uzytkownika ("czy wszystko dziala idealnie tak samo") - przed ta poprawka
detect_phase()/COUNTRY_PATTERNS w Pythonie byly znaczaco uproszczonymi wersjami monolitu."""
from app.modules.parser.core_elektryka import core_and_attrs, detect_phase


# ---- detect_phase(): heurystyka koloru CEE (gniazda/wtyczki sily bez jawnego "1F"/"3F") ----

def test_detect_phase_niebieski_bez_jawnej_fazy_to_1f():
    assert detect_phase("Wtyczka odbiornikowa 32A niebieska") == "1F"


def test_detect_phase_czerwony_bez_jawnej_fazy_to_3f():
    assert detect_phase("Wtyczka przenośna 32A 3 fazowa (czerwona)") == "3F"


def test_detect_phase_niebieski_poza_kontekstem_cee_nie_wplywa():
    # "niebieski" samo w sobie NIE wystarcza - wymagany kontekst gniazdo/wtyczka/... (patrz JS isCEE)
    assert detect_phase("Przewód niebieski 3x1,5") is None


def test_detect_phase_kolor_angielski_blue_red():
    assert detect_phase("Gniazdo blue 16A") == "1F"
    assert detect_phase("Gniazdo red 32A") == "3F"


# ---- detect_phase(): napiecie ----

def test_detect_phase_napiecie_230v_to_1f():
    assert detect_phase("Wyłącznik 230V") == "1F"


def test_detect_phase_napiecie_400v_to_3f():
    assert detect_phase("Wyłącznik 400V") == "3F"


# ---- detect_phase(): zapis biegunowy ----

def test_detect_phase_2p_plus_pe_to_1f():
    assert detect_phase("Wtyczka 2P+PE") == "1F"


def test_detect_phase_3p_n_pe_to_3f():
    assert detect_phase("Wtyczka 3P+N+PE") == "3F"


def test_detect_phase_5p_to_3f():
    assert detect_phase("Wtyczka 5P 32A") == "3F"


# ---- detect_phase(): slownie/skroty (juz dzialalo wczesniej, regresja) ----

def test_detect_phase_jednofazowa_slownie():
    assert detect_phase("Różnicówka jednofazowa") == "1F"


def test_detect_phase_trojfazowa_slownie():
    assert detect_phase("Różnicówka trójfazowa") == "3F"


def test_detect_phase_1f_3f_skrot():
    assert detect_phase("Gniazdo 1F 16A") == "1F"
    assert detect_phase("Gniazdo 3F 32A") == "3F"


def test_detect_phase_brak_wskazowek_zwraca_none():
    assert detect_phase("Rozdzielnica SRN 12") is None


def test_gniazdo_odbiornikowe_oznacza_montaz_staly():
    assert core_and_attrs("Gniazdo odbiornikowe 3F 16A").montaz == "STALY"


# ---- COUNTRY_PATTERNS: warianty tolerancyjne na literowki OCR + skroty ----

def test_country_niemiecki_literowka_brak_e():
    assert core_and_attrs("Bezpiecznik niemicki 16A").country == "DE"


def test_country_niemiecki_literowka_brak_c():
    assert core_and_attrs("Bezpiecznik niemieki 16A").country == "DE"


def test_country_bare_skrot_de():
    assert core_and_attrs("Gniazdo DE 16A").country == "DE"


def test_country_bare_skrot_pl():
    assert core_and_attrs("Gniazdo PL 16A").country == "PL"


def test_country_standardowy_niemiecki_nadal_dziala():
    assert core_and_attrs("Bezpiecznik niemiecki 16A").country == "DE"
