from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.search import FlightCombination, SearchRequest


class ProviderError(Exception):
    """Raised when an upstream flight data provider fails or is misconfigured."""


class FlightProvider(ABC):
    """Interface every flight data source must implement.

    Kiwi Tequila is the first implementation; Amadeus Flight Offers Search
    (or others) can be added later by implementing the same interface.
    """

    @abstractmethod
    async def search(self, criteria: SearchRequest) -> list[FlightCombination]:
        raise NotImplementedError
