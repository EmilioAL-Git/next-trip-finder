"""Shared date-pair grid builder for providers with no native flexible-date search.

Duffel and Google Flights (via fast-flights) only accept one exact date per
leg, so providers that use them enumerate the valid (outbound_date,
return_date) combinations themselves and sample a bounded subset to keep API
usage predictable.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.schemas.search import SearchRequest


def build_date_grid(criteria: SearchRequest) -> list[tuple[date, date]]:
    pairs: list[tuple[date, date]] = []
    outbound_span = (criteria.outbound_date_to - criteria.outbound_date_from).days

    for offset in range(outbound_span + 1):
        outbound = criteria.outbound_date_from + timedelta(days=offset)
        lo_nights = criteria.min_nights if criteria.min_nights is not None else 1
        hi_nights = (
            criteria.max_nights
            if criteria.max_nights is not None
            else max(lo_nights, (criteria.return_date_to - outbound).days)
        )
        for nights in range(lo_nights, hi_nights + 1):
            return_date = outbound + timedelta(days=nights)
            if criteria.return_date_from <= return_date <= criteria.return_date_to:
                pairs.append((outbound, return_date))

    return pairs


def sample_pairs(pairs: list[tuple[date, date]], cap: int) -> list[tuple[date, date]]:
    if len(pairs) <= cap:
        return pairs
    step = len(pairs) / cap
    return [pairs[int(i * step)] for i in range(cap)]
