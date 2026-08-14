from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.providers.base import FlightProvider, ProviderError
from app.providers.duffel import DuffelProvider
from app.providers.google_flights import GoogleFlightsProvider
from app.providers.kiwi import KiwiTequilaProvider
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_engine import SearchEngine

router = APIRouter()


def build_provider(settings: Settings) -> FlightProvider:
    if settings.flight_provider == "kiwi":
        return KiwiTequilaProvider(settings)
    if settings.flight_provider == "duffel":
        return DuffelProvider(settings)
    if settings.flight_provider == "google":
        return GoogleFlightsProvider(settings)
    raise ProviderError(f"Proveedor de vuelos desconocido: {settings.flight_provider!r}")


def get_search_engine(settings: Settings = Depends(get_settings)) -> SearchEngine:
    return SearchEngine(build_provider(settings))


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/search", response_model=SearchResponse)
async def search_flights(
    criteria: SearchRequest,
    engine: SearchEngine = Depends(get_search_engine),
) -> SearchResponse:
    return await engine.search(criteria)
