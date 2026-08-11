# Raport — usunięcie timing-attacku przy logowaniu (enumeracja kont)

Znalezisko z niezależnego przeglądu kodu (branch `agent/fix-multiplexer-review-findings`),
obszar `backend/app/modules/users/` — dotyczy `POST /auth/token`, istniało od Etapu 5, nie
zostało wprowadzone przez `RAPORT_BEZPIECZENSTWO_1.md`.

## Przyczyna

```python
user = repository.get_user_by_email(session, form_data.username)
if user is None or not user.active or not verify_password(form_data.password, user.hashed_password):
```

`or` w Pythonie jest leniwy — `verify_password()` (bcrypt, ~100 ms) wykonuje się TYLKO gdy
`user` istnieje i jest aktywny. Dla nieistniejącego/nieaktywnego konta funkcja wraca prawie
natychmiast. Różnica czasu odpowiedzi (~100 ms vs. ~1 ms) zdradza, czy podany e-mail jest
zarejestrowany w systemie, niezależnie od treści komunikatu błędu (który jest identyczny w obu
przypadkach) — pozwala to na enumerację prawdziwych adresów kont przed próbą brute-force lub
phishingiem, mierząc czas odpowiedzi z zewnątrz.

## Co zostało zrobione

- `security.py`: nowa stała `DUMMY_PASSWORD_HASH` — jeden, stały (wygenerowany raz, nie przy
  każdym żądaniu) hash bcrypt placeholdera, używany wyłącznie do wyrównania czasu.
- `router.py: login()`: `verify_password()` wywoływane teraz ZAWSZE — dla nieistniejącego konta
  hasło jest weryfikowane wobec `DUMMY_PASSWORD_HASH` zamiast krótko-obwodzenia wywołania.
  Rezultat (`False`) i dalsza logika (`user is None or ...`) bez zmian — konto nieistniejące
  wciąż dostaje `401` z tym samym komunikatem, tylko teraz w tym samym czasie co błędne hasło na
  koncie istniejącym.
- Blokada per-konto (`lockout.py`) i rate limiting per-IP nie wymagały zmian — obie działają na
  `form_data.username` niezależnie od tego, czy konto istnieje, więc próg 5 prób dotyczy
  identycznie prawdziwych i nieprawdziwych adresów.

## Testy

- `tests/test_auth.py` (+1 test): `test_login_nieistniejacego_uzytkownika_i_tak_liczy_bcrypt` —
  podmienia `verify_password` na szpiega i sprawdza, że dla nieistniejącego e-maila funkcja
  została wywołana z `DUMMY_PASSWORD_HASH` (nie pominięta).
- **Pełna suita: 346 → 347 testów backendu, zero regresji.**

## Jak zweryfikować

```bash
cd backend
pytest tests/test_auth.py tests/test_auth_lockout.py -v
pytest tests/ -q   # 347 testow, 1 pominiety
```
