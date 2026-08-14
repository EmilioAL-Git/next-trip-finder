from __future__ import annotations

import asyncio
from datetime import date, datetime

import httpx

from app.config import Settings
from app.providers.base import FlightProvider, ProviderError
from app.providers.date_grid import build_date_grid, sample_pairs
from app.providers.regions import EUROPE_EXPLORATION_DESTINATIONS
from app.schemas.search import FlightCombination, FlightLeg, SearchRequest

OFFER_REQUESTS_PATH = "/air/offer_requests"


class DuffelProvider(FlightProvider):
    """Client for the Duffel Offer Requests API.

    Duffel has no flexible-date or destination-discovery endpoint, so this
    provider builds its own grid of (outbound_date, return_date) pairs from
    the requested ranges/duration, and searches a bounded, evenly-sampled
    subset of that grid per destination (capped by
    `duffel_max_total_searches` to keep API usage predictable). Duffel does
    support per-slice `departure_time` windows natively, so those are passed
    through; `SearchEngine` re-applies every filter afterwards regardless.
    """

    def __init__(self, settings: Settings):
        if not settings.duffel_access_token:
            raise ProviderError("DUFFEL_ACCESS_TOKEN no configurado")
        self._access_token = settings.duffel_access_token
        self._base_url = settings.duffel_base_url
        self._version = settings.duffel_version
        self._timeout = settings.request_timeout_seconds
        self._max_total_searches = max(1, settings.duffel_max_total_searches)

    async def search(self, criteria: SearchRequest) -> list[FlightCombination]:
        destinations = criteria.destinations or EUROPE_EXPLORATION_DESTINATIONS
        grid = build_date_grid(criteria)
        if not grid:
            return []

        per_destination_cap = max(1, self._max_total_searches // len(destinations))
        sampled_pairs = sample_pairs(grid, per_destination_cap)

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Duffel-Version": self._version,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            tasks = [
                self._search_pair(client, headers, criteria.origin, destination, outbound, ret, criteria)
                for destination in destinations
                for outbound, ret in sampled_pairs
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        combos: list[FlightCombination] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            combos.extend(result)
        return combos

    async def _search_pair(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        origin: str,
        destination: str,
        outbound_date: date,
        return_date: date,
        criteria: SearchRequest,
    ) -> list[FlightCombination]:
        outbound_slice: dict = {
            "origin": origin,
            "destination": destination,
            "departure_date": outbound_date.isoformat(),
        }
        inbound_slice: dict = {
            "origin": destination,
            "destination": origin,
            "departure_date": return_date.isoformat(),
        }
        if criteria.outbound_departure_window:
            outbound_slice["departure_time"] = {
                "from": criteria.outbound_departure_window.from_time.strftime("%H:%M"),
                "to": criteria.outbound_departure_window.to_time.strftime("%H:%M"),
            }
        if criteria.return_departure_window:
            inbound_slice["departure_time"] = {
                "from": criteria.return_departure_window.from_time.strftime("%H:%M"),
                "to": criteria.return_departure_window.to_time.strftime("%H:%M"),
            }

        body = {
            "data": {
                "slices": [outbound_slice, inbound_slice],
                "passengers": [{"type": "adult"}],
                "cabin_class": "economy",
            }
        }

        try:
            response = await client.post(
                OFFER_REQUESTS_PATH,
                params={"return_offers": "true"},
                json=body,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"Duffel devolvió {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"No se pudo contactar con Duffel: {exc}") from exc

        offers = response.json().get("data", {}).get("offers", [])
        return [self._parse_offer(offer, destination) for offer in offers if len(offer.get("slices", [])) >= 2]

    @staticmethod
    def _parse_offer(offer: dict, destination: str) -> FlightCombination:
        slices = offer["slices"]
        outbound = DuffelProvider._build_leg(slices[0]["segments"])
        inbound = DuffelProvider._build_leg(slices[1]["segments"])
        nights = (inbound.departure.date() - outbound.arrival.date()).days

        return FlightCombination(
            destination_code=destination,
            destination_city=destination,
            outbound=outbound,
            inbound=inbound,
            nights=max(nights, 0),
            price=float(offer.get("total_amount", 0)),
            currency=offer.get("total_currency", ""),
            booking_url="",
        )

    @staticmethod
    def _build_leg(segments: list[dict]) -> FlightLeg:
        first, last = segments[0], segments[-1]
        departure = datetime.fromisoformat(first["departing_at"])
        arrival = datetime.fromisoformat(last["arriving_at"])
        airlines = sorted(
            {
                seg.get("operating_carrier", {}).get("iata_code") or seg.get("operating_carrier", {}).get("name", "")
                for seg in segments
                if seg.get("operating_carrier")
            }
        )
        duration_minutes = int((arrival - departure).total_seconds() // 60)

        return FlightLeg(
            origin=first["origin"]["iata_code"],
            destination=last["destination"]["iata_code"],
            departure=departure,
            arrival=arrival,
            airlines=[a for a in airlines if a],
            stops=len(segments) - 1,
            duration_minutes=duration_minutes,
        )
