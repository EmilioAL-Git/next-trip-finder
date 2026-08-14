from __future__ import annotations

import asyncio
from datetime import date, datetime

from fast_flights import FlightQuery, Passengers, create_query, get_flights
from fast_flights.exceptions import FlightsNotFound
from fast_flights.fetcher import URL as GOOGLE_FLIGHTS_URL
from fast_flights.integrations.base import FetchIntegration
from fast_flights.model import Flights, SingleFlight
from primp import Client as PrimpClient

from app.config import Settings
from app.providers.base import FlightProvider, ProviderError
from app.providers.date_grid import build_date_grid, sample_pairs
from app.providers.regions import EUROPE_EXPLORATION_DESTINATIONS
from app.schemas.search import FlightCombination, FlightLeg, SearchRequest

# Google shows an EU cookie-consent interstitial instead of flight results
# for traffic it treats as EU-region, which the underlying library doesn't
# handle (see https://github.com/AWeirdDev/flights/issues/46, closed
# upstream as "not planned" — never merged). Pre-setting this SOCS consent
# cookie skips the interstitial. Confirmed working as of this implementation;
# Google could invalidate this value at any time without notice.
_SOCS_CONSENT_COOKIE = "CAESHwgBEhJnd3NfMjAyNTAyMjctMF9SQzIaBXpoLUNOIAEaBgiAy6O-Bg"


class _ConsentCookieFetch(FetchIntegration):
    def __init__(self, proxy: str | None):
        self._proxy = proxy

    def fetch_html(self, q) -> str:  # noqa: ANN001 - matches FetchIntegration's untyped `q`
        client = PrimpClient(
            impersonate="chrome_145",
            impersonate_os="macos",
            referer=True,
            proxy=self._proxy,
            cookie_store=True,
        )
        params = q.params() if not isinstance(q, str) else {"q": q}
        response = client.get(
            GOOGLE_FLIGHTS_URL, params=params, headers={"Cookie": f"SOCS={_SOCS_CONSENT_COOKIE}"}
        )
        return response.text


class GoogleFlightsProvider(FlightProvider):
    """Client for Google Flights via the unofficial `fast-flights` library.

    Not an official API: it decodes the same protobuf payload Google Flights'
    own web UI sends, with no partner agreement, no rate-limit guarantees,
    and no notice if Google changes the format or blocks the traffic. It's
    used here because it's the only source in this project that's free with
    real prices/times.

    Two limitations shape the implementation:

    1. No flexible-date or destination-discovery endpoint — same as Duffel,
       so it reuses `date_grid` to enumerate and sample candidate
       (outbound_date, return_date) pairs.
    2. Its `trip="round-trip"` mode only ever returns outbound-leg options,
       never a combined itinerary with the return leg (confirmed against
       live data; a known, unfixed upstream limitation). So each candidate
       date pair is searched as two independent one-way queries, and the
       cheapest few options from each are cross-joined locally. The
       resulting price is the SUM of two one-way fares, which approximates
       but does not guarantee the true bundled round-trip fare an airline
       might offer.
    """

    def __init__(self, settings: Settings):
        self._max_total_searches = max(1, settings.google_flights_max_total_searches)
        self._max_concurrency = max(1, settings.google_flights_max_concurrency)
        self._top_options_per_leg = max(1, settings.google_flights_top_options_per_leg)
        self._fetch_integration = _ConsentCookieFetch(settings.google_flights_proxy or None)

    async def search(self, criteria: SearchRequest) -> list[FlightCombination]:
        destinations = criteria.destinations or EUROPE_EXPLORATION_DESTINATIONS
        grid = build_date_grid(criteria)
        if not grid:
            return []

        # Each date-pair candidate costs 2 real requests (outbound + inbound leg).
        per_destination_cap = max(1, self._max_total_searches // (2 * len(destinations)))
        sampled_pairs = sample_pairs(grid, per_destination_cap)

        semaphore = asyncio.Semaphore(self._max_concurrency)
        tasks = [
            self._search_pair(semaphore, criteria.origin, destination, outbound, ret, criteria)
            for destination in destinations
            for outbound, ret in sampled_pairs
        ]
        results = await asyncio.gather(*tasks)

        combos: list[FlightCombination] = []
        for result in results:
            combos.extend(result)
        return combos

    async def _search_pair(
        self,
        semaphore: asyncio.Semaphore,
        origin: str,
        destination: str,
        outbound_date: date,
        return_date: date,
        criteria: SearchRequest,
    ) -> list[FlightCombination]:
        outbound_options, inbound_options = await asyncio.gather(
            self._search_leg(semaphore, origin, destination, outbound_date, criteria.currency),
            self._search_leg(semaphore, destination, origin, return_date, criteria.currency),
        )

        combos = []
        for out_entry in outbound_options:
            for in_entry in inbound_options:
                combos.append(self._build_combination(out_entry, in_entry, destination, criteria.currency))
        return combos

    async def _search_leg(
        self,
        semaphore: asyncio.Semaphore,
        origin: str,
        destination: str,
        leg_date: date,
        currency: str,
    ) -> list[Flights]:
        # The `fast-flights` version on PyPI (3.0.2) doesn't expose the
        # per-leg earliest/latest departure hour filters that its
        # not-yet-released dev branch has, so this leg search is unfiltered
        # by time; `SearchEngine` is what actually enforces the requested
        # departure window afterwards.
        query = create_query(
            flights=[
                FlightQuery(
                    date=leg_date.isoformat(),
                    from_airport=origin,
                    to_airport=destination,
                )
            ],
            trip="one-way",
            passengers=Passengers(adults=1),
            currency=currency,
        )

        async with semaphore:
            try:
                result = await asyncio.to_thread(get_flights, query, integration=self._fetch_integration)
            except FlightsNotFound:
                return []
            except Exception as exc:  # noqa: BLE001 - unofficial scraper, failures vary widely
                raise ProviderError(f"Google Flights (no oficial) falló para {origin}->{destination}: {exc}") from exc

        return list(result)[: self._top_options_per_leg]

    @staticmethod
    def _build_combination(out_entry: Flights, in_entry: Flights, destination: str, currency: str) -> FlightCombination:
        outbound = GoogleFlightsProvider._build_leg(out_entry.flights, out_entry.airlines)
        inbound = GoogleFlightsProvider._build_leg(in_entry.flights, in_entry.airlines)
        nights = (inbound.departure.date() - outbound.arrival.date()).days

        return FlightCombination(
            destination_code=destination,
            destination_city=destination,
            outbound=outbound,
            inbound=inbound,
            nights=max(nights, 0),
            price=float(out_entry.price) + float(in_entry.price),
            currency=currency,
            booking_url="",
        )

    @staticmethod
    def _build_leg(segments: list[SingleFlight], airlines: list[str]) -> FlightLeg:
        first, last = segments[0], segments[-1]
        departure = datetime(*first.departure.date, *first.departure.time)
        arrival = datetime(*last.arrival.date, *last.arrival.time)
        duration_minutes = int((arrival - departure).total_seconds() // 60)

        return FlightLeg(
            origin=first.from_airport.code,
            destination=last.to_airport.code,
            departure=departure,
            arrival=arrival,
            airlines=list(airlines),
            stops=len(segments) - 1,
            duration_minutes=duration_minutes,
        )
