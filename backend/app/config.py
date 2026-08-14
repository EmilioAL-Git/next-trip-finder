from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    flight_provider: str = "google"  # "google" (free, unofficial) | "duffel" (paid, official) | "kiwi" (invite-only)

    tequila_api_key: str = ""
    tequila_base_url: str = "https://api.tequila.kiwi.com"

    duffel_access_token: str = ""
    duffel_base_url: str = "https://api.duffel.com"
    duffel_version: str = "v2"
    duffel_max_total_searches: int = 40

    google_flights_max_total_searches: int = 40
    google_flights_max_concurrency: int = 5
    google_flights_proxy: str = ""
    google_flights_top_options_per_leg: int = 5

    default_currency: str = "EUR"
    allowed_origins: str = "http://localhost:8080"
    request_timeout_seconds: float = 20.0

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
