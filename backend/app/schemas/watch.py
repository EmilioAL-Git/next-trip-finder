"""Data model reserved for the future price-watch feature (not wired up yet).

Intended flow: persist a SavedSearch, re-run it periodically, and notify
(e.g. via Telegram/n8n) when the cheapest result drops below `notify_below`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.search import SearchRequest


class SavedSearch(BaseModel):
    id: str
    owner: str
    criteria: SearchRequest
    notify_below: float | None = None
    created_at: datetime
    last_checked_at: datetime | None = None
    last_best_price: float | None = None
