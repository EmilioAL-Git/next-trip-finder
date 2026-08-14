from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator


class TimeWindow(BaseModel):
    """Departure time-of-day window, e.g. 06:00-12:00 local time."""

    from_time: time
    to_time: time

    @model_validator(mode="after")
    def check_order(self) -> "TimeWindow":
        if self.from_time >= self.to_time:
            raise ValueError("from_time must be earlier than to_time")
        return self


class SearchRequest(BaseModel):
    origin: str = Field(..., min_length=3, description="IATA airport/city code, e.g. MAD")
    destinations: list[str] = Field(
        default_factory=list,
        description="IATA codes to compare. Empty list means 'any destination'.",
    )

    outbound_date_from: date
    outbound_date_to: date
    return_date_from: date
    return_date_to: date

    min_nights: int | None = Field(default=None, ge=0, le=365)
    max_nights: int | None = Field(default=None, ge=0, le=365)

    outbound_departure_window: TimeWindow | None = None
    return_departure_window: TimeWindow | None = None

    currency: str = Field(default="EUR", min_length=3, max_length=3)
    max_results: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def check_ranges(self) -> "SearchRequest":
        if self.outbound_date_from > self.outbound_date_to:
            raise ValueError("outbound_date_from must not be after outbound_date_to")
        if self.return_date_from > self.return_date_to:
            raise ValueError("return_date_from must not be after return_date_to")
        if self.return_date_from < self.outbound_date_from:
            raise ValueError("return_date_from must not be before outbound_date_from")
        if (
            self.min_nights is not None
            and self.max_nights is not None
            and self.min_nights > self.max_nights
        ):
            raise ValueError("min_nights must not be greater than max_nights")
        return self


class FlightLeg(BaseModel):
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    airlines: list[str]
    stops: int
    duration_minutes: int


class FlightCombination(BaseModel):
    destination_code: str
    destination_city: str
    outbound: FlightLeg
    inbound: FlightLeg
    nights: int
    price: float
    currency: str
    booking_url: str


class SearchResponse(BaseModel):
    count: int
    results: list[FlightCombination]
