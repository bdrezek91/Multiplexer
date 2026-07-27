"""Konfiguracja aplikacji (Etap 2: adres bazy danych)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://multiplekser:multiplekser_dev@localhost:5432/multiplekser"


settings = Settings()
