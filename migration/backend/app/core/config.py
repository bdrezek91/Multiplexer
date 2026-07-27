"""Konfiguracja aplikacji (Etap 2: adres bazy danych; Etap 5: JWT; Etap 6: klucze OCR;
Etap 7: Redis/Celery + MinIO/S3)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://multiplekser:multiplekser_dev@localhost:5432/multiplekser"

    redis_url: str = "redis://localhost:6379/0"

    # MinIO domyslnie (docker-compose.yml) - S3-kompatybilne, wiec ten sam klient (boto3) dziala
    # bez zmian tez z prawdziwym AWS S3 czy Azure Blob (S3 gateway) - wystarczy zmienic endpoint.
    minio_endpoint_url: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "multiplekser-dokumenty"

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
    ocr_timeout_seconds: int = 90

    # Skalowanie zdjec (nie-PDF) przed wyslaniem do AI - mniejszy upload = szybsza odpowiedz.
    ocr_image_max_side: int = 1800
    ocr_image_quality: int = 85


settings = Settings()
