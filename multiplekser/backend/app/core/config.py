"""Konfiguracja aplikacji (Etap 2: adres bazy danych; Etap 5: JWT; Etap 6: klucze OCR;
Etap 7: Redis/Celery + MinIO/S3)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://multiplekser:multiplekser_dev@localhost:5432/multiplekser"

    redis_url: str = "redis://localhost:6379/0"

    # Poziom strukturalnego logowania (Etap "quick winy") - patrz app/core/logging_config.py.
    log_level: str = "INFO"

    # MinIO domyslnie (docker-compose.yml) - S3-kompatybilne, wiec ten sam klient (boto3) dziala
    # bez zmian tez z prawdziwym AWS S3 czy Azure Blob (S3 gateway) - wystarczy zmienic endpoint.
    minio_endpoint_url: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "multiplekser-dokumenty"

    # Maksymalna liczba najnowszych analiz przechowywanych razem z plikami zrodlowymi.
    # Retencja usuwa tylko zakonczone dokumenty (done/error); queued/processing sa chronione.
    document_retention_limit: int = 20

    # UWAGA: wartosc domyslna jest TYLKO do dewelopmentu lokalnego - w produkcji MUSI byc
    # nadpisana zmienna srodowiskowa JWT_SECRET_KEY (losowy, dlugi sekret).
    jwt_secret_key: str = "dev-insecure-secret-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Klucze Gemini - WYLACZNIE ze zmiennych srodowiskowych (GEMINI_API_KEY_FREE/_PAID).
    # NIGDY nie wpisywac tu wartosci na sztywno - patrz RAPORT_ETAP_6.md, zastrzezenie
    # bezpieczenstwa: monolit (index.html) mial klucze zaszyte w kodzie, co jest wyciekiem.
    gemini_api_key_free: str | None = None
    gemini_api_key_paid: str | None = None
    # Skrocone z 90s (2026-08-04, na zyczenie uzytkownika - przetwarzanie calego dokumentu
    # trwalo 2-3 minuty, za dlugo) - przy opornym/przeciazonym kroku lancucha lepiej szybciej
    # poddac sie i przejsc do kolejnego kroku (patrz chain.py) niz czekac az do 90s na kazdym
    # z kilku sekwencyjnych zapytan (klasyfikacja + pelny odczyt) z osobna.
    ocr_timeout_seconds: int = 30

    # Klucz OpenAI - OSTATNI krok w default_ocr_chain() (patrz ocr/chain.py), uzywany WYLACZNIE
    # gdy wszystkie kroki Gemini zawioda (429/timeout/limit) - nie przy kazdym dokumencie.
    # Opcjonalny - brak klucza po prostu pomija ten krok, tak jak brak klucza Gemini platnego.
    #
    # Historia (2026-08-04): pierwsza wersja probowala OpenAI jako niezalezny cross-check
    # (rownolegly drugi odczyt przy KAZDYM dokumencie, flagujacy rozbieznosci) - porzucone na
    # zyczenie uzytkownika po tym, jak "gpt-4o-mini" w tej roli znajdowal ulamek pozycji Gemini
    # (1 z kilkunastu), przez co prawie wszystko bylo falszywie oznaczane "do weryfikacji".
    # Prosty fallback na koncu tego samego lancucha okazal sie skuteczniejszy i tanszy.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # Skalowanie zdjec (nie-PDF) przed wyslaniem do AI - mniejszy upload = szybsza odpowiedz.
    # Podniesione z 1800/85 (port 1:1 z monolitu) - realny przypadek z produkcji (patrz
    # docs/RAPORT_OCR_NIEZAWODNOSC_1.md): drobne odreczne znaki (np. cyfra "1" tuz obok ptaszka
    # potwierdzenia) tracily wyrazistosc przy kompresji, model czasem nie mial pewnosci czy to
    # cyfra czy sam ptaszek. Wyzsza rozdzielczosc/jakosc kosztuje kilka sekund dluzszy upload,
    # ale zachowuje wiecej szczegolow drobnego pisma - w parze z doprecyzowanym promptem (patrz
    # ocr/prompt.py, _ZNACZNIKI_DOPISEK).
    ocr_image_max_side: int = 2600
    ocr_image_quality: int = 95


settings = Settings()
