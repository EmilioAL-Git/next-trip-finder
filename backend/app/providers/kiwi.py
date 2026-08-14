from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.providers.base import FlightProvider, ProviderError
from app.schemas.search import FlightCombination, FlightLeg, SearchRequest

SEARCH_PATH = "/v2/search"


class KiwiTequilaProvider(FlightProvider):
    """Client for the Kiwi Tequila /v2/search endpoint.

    Tequila supports date ranges and independent departure-time windows for
    the outbound and return legs natively, so the heavy filtering happens
    server-side; the search engine layer re-checks results defensively.
    """

    def __init__(self, settings: Settings):
        if not settings.tequila_api_key:
            raise ProviderError("TEQUILA_API_KEY is not configured")
        self._api_key = settings.tequila_api_key
        self._base_url = settings.tequila_base_url
        self._timeout = settings.request_timeout_seconds

    async def search(self, criteria: SearchRequest) -> list[FlightCombination]:
        params = self._build_params(criteria)
        headers = {"apikey": self._api_key}

        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            try:
                response = await client.get(SEARCH_PATH, params=params, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ProviderError(
                    f"Tequila API returned {exc.response.status_code}: {exc.response.text[:300]}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(f"Failed to reach Tequila API: {exc}") from exc

        payload = response.json()
        return [self._parse_itinerary(item, criteria.currency) for item in payload.get("data", [])]

    @staticmethod
    def _build_params(criteria: SearchRequest) -> dict[str, str | int]:
        params: dict[str, str | int] = {
            "fly_from": criteria.origin,
            "fly_to": ",".join(criteria.destinations) if criteria.destinations else "anywhere",
            "date_from": criteria.outbound_date_from.strftime("%d/%m/%Y"),
            "date_to": criteria.outbound_date_to.strftime("%d/%m/%Y"),
            "return_from": criteria.return_date_from.strftime("%d/%m/%Y"),
            "return_to": criteria.return_date_to.strftime("%d/%m/%Y"),
            "curr": criteria.currency,
            "sort": "price",
            "asc": 1,
            "limit": criteria.max_results,
            "one_for_city": 0 if criteria.destinations else 1,
        }

        if criteria.min_nights is not None:
            params["nights_in_dst_from"] = criteria.min_nights
        if criteria.max_nights is not None:
            params["nights_in_dst_to"] = criteria.max_nights

        if criteria.outbound_departure_window is not None:
            params["dtime_from"] = criteria.outbound_departure_window.from_time.strftime("%H:%M")
            params["dtime_to"] = criteria.outbound_departure_window.to_time.strftime("%H:%M")

        if criteria.return_departure_window is not None:
            params["ret_dtime_from"] = criteria.return_departure_window.from_time.strftime("%H:%M")
            params["ret_dtime_to"] = criteria.return_departure_window.to_time.strftime("%H:%M")

        return params

    @staticmethod
    def _parse_itinerary(item: dict, currency: str) -> FlightCombination:
        route = item.get("route", [])
        outbound_segments = [seg for seg in route if seg.get("return") == 0]
        inbound_segments = [seg for seg in route if seg.get("return") == 1]

        if not outbound_segments or not inbound_segments:
            raise ProviderError("Unexpected itinerary shape from Tequila API (missing leg)")

        outbound = KiwiTequilaProvider._build_leg(outbound_segments)
        inbound = KiwiTequilaProvider._build_leg(inbound_segments)
        nights = (inbound.departure.date() - outbound.arrival.date()).days

        return FlightCombination(
            destination_code=item.get("flyTo", inbound_segments[0].get("cityFrom", "")),
            destination_city=item.get("cityTo", ""),
            outbound=outbound,
            inbound=inbound,
            nights=max(nights, 0),
            price=float(item.get("price", 0)),
            currency=currency,
            booking_url=item.get("deep_link", ""),
        )

    @staticmethod
    def _build_leg(segments: list[dict]) -> FlightLeg:
        first, last = segments[0], segments[-1]
        departure = KiwiTequilaProvider._parse_segment_time(first, "dTime", "local_departure")
        arrival = KiwiTequilaProvider._parse_segment_time(last, "aTime", "local_arrival")
        airlines = sorted({seg.get("airline", "") for seg in segments if seg.get("airline")})
        duration_minutes = int((arrival - departure).total_seconds() // 60)

        return FlightLeg(
            origin=first.get("cityFrom", first.get("flyFrom", "")),
            destination=last.get("cityTo", last.get("flyTo", "")),
            departure=departure,
            arrival=arrival,
            airlines=airlines,
            stops=len(segments) - 1,
            duration_minutes=duration_minutes,
        )

    @staticmethod
    def _parse_segment_time(segment: dict, unix_key: str, local_key: str) -> datetime:
        """Prefer the airport-local timestamp Tequila provides; fall back to UTC unix time."""
        local_value = segment.get(local_key)
        if local_value:
            return datetime.fromisoformat(str(local_value).replace("Z", "+00:00"))
        return datetime.fromtimestamp(segment[unix_key], tz=timezone.utc)
