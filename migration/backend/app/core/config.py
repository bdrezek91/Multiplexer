"""Konfiguracja aplikacji (Etap 2: adres bazy danych; Etap 5: JWT)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://multiplekser:multiplekser_dev@localhost:5432/multiplekser"

    # UWAGA: wartosc domyslna jest TYLKO do dewelopmentu lokalnego - w produkcji MUSI byc
    # nadpisana zmienna srodowiskowa JWT_SECRET_KEY (losowy, dlugi sekret).
    jwt_secret_key: str = "dev-insecure-secret-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7


settings = Settings()
