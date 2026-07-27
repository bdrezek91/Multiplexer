# Jak zacząć pracę z Claude Code w tym repo

## 1. Przygotowanie repozytorium

Jeśli jeszcze nie masz tego w Gicie:

```bash
cd migration          # ten folder
git init
git add .
git commit -m "Etap 0-1: analiza + szkielet + Matcher/Parser w Pythonie"
```

Utwórz puste repo na GitHubie (bez README, bez .gitignore — masz już swoje pliki), potem:

```bash
git remote add origin https://github.com/TWOJA_NAZWA/multiplekser-elektryka-saas.git
git branch -M main
git push -u origin main
```

## 2. Instalacja Claude Code

Jeśli jeszcze nie masz: https://docs.claude.com/en/docs/claude-code — instrukcje instalacji dla
Twojego systemu (Node.js wymagany). W skrócie zwykle:

```bash
npm install -g @anthropic-ai/claude-code
```

## 3. Uruchomienie w repo

```bash
cd multiplekser-elektryka-saas
claude
```

Claude Code automatycznie wczyta plik `CLAUDE.md` z tego repo jako kontekst projektu — nie musisz
mu tłumaczyć wszystkiego od nowa w każdej sesji.

## 4. Pierwsza wiadomość do wklejenia

Przy pierwszym uruchomieniu w tym repo wklej:

```
Przeczytaj CLAUDE.md i docs/RAPORT_ETAP_1.md. Potwierdź że rozumiesz stan projektu i zasady
migracji, uruchom istniejące testy (pytest w backend/), a potem krótko zaproponuj plan Etapu 2
(model danych PostgreSQL + Alembic + import katalogu) - zanim zaczniesz pisać kod, poczekaj na
moje potwierdzenie planu.
```

## 5. Dalsza praca

Po zaakceptowaniu planu Etapu 2, w kolejnych wiadomościach po prostu kontynuuj rozmowę normalnie
("ok, zaczynaj", pytania, poprawki). Claude Code będzie pracował w małych krokach i zatrzyma się
na końcu etapu zgodnie z zasadami w `CLAUDE.md`.

Jeśli chcesz podać oryginalny plik monolitu (`Multiplekser_Elektryka.html`) do wglądu przy
kolejnych etapach (np. Etap 4 — moduł OCR, którego jeszcze nie przenosiłem) — po prostu wrzuć go
do repo (np. `legacy/Multiplekser_Elektryka.html`) i wspomnij o tym Claude Code w wiadomości.
