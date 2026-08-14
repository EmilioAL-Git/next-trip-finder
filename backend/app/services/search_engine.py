from __future__ import annotations

from datetime import time

from app.providers.base import FlightProvider
from app.schemas.search import FlightCombination, SearchRequest, SearchResponse, TimeWindow


class SearchEngine:
    """Orchestrates a provider search and enforces the requested filters.

    The provider (e.g. Kiwi Tequila) already applies date/time/duration
    filters server-side, but we re-check them here as a safety net so the
    API contract ("only matching combinations, never everything") holds
    regardless of provider quirks.
    """

    def __init__(self, provider: FlightProvider):
        self._provider = provider

    async def search(self, criteria: SearchRequest) -> SearchResponse:
        combinations = await self._provider.search(criteria)
        filtered = [c for c in combinations if self._matches(c, criteria)]
        filtered.sort(key=lambda c: c.price)
        trimmed = filtered[: criteria.max_results]
        return SearchResponse(count=len(trimmed), results=trimmed)

    @staticmethod
    def _matches(combo: FlightCombination, criteria: SearchRequest) -> bool:
        if not (criteria.outbound_date_from <= combo.outbound.departure.date() <= criteria.outbound_date_to):
            return False
        if not (criteria.return_date_from <= combo.inbound.departure.date() <= criteria.return_date_to):
            return False
        if criteria.min_nights is not None and combo.nights < criteria.min_nights:
            return False
        if criteria.max_nights is not None and combo.nights > criteria.max_nights:
            return False
        if not SearchEngine._within_window(combo.outbound.departure.time(), criteria.outbound_departure_window):
            return False
        if not SearchEngine._within_window(combo.inbound.departure.time(), criteria.return_departure_window):
            return False
        return True

    @staticmethod
    def _within_window(value: time, window: TimeWindow | None) -> bool:
        if window is None:
            return True
        return window.from_time <= value <= window.to_time
