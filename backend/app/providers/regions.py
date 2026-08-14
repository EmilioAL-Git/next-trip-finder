"""Curated destination shortlist for 'any destination' exploration mode.

Duffel has no discovery/inspiration endpoint (unlike Tequila's fly_to=anywhere
or Amadeus's now-decommissioned Flight Inspiration Search), so exploring
"any destination" means searching a fixed list of candidates ourselves. This
list favours popular European hubs and leisure destinations per the user's
stated focus on Europe. Pass explicit `destinations` in the request for
anything outside this list.
"""

EUROPE_EXPLORATION_DESTINATIONS: list[str] = [
    "LIS", "FCO", "CDG", "AMS", "LHR", "MXP", "ATH", "BER", "MUC", "VIE",
    "PRG", "BUD", "DUB", "CPH", "ARN", "OSL", "WAW", "IST", "NCE", "PMI",
    "ZRH", "BRU", "HEL", "OPO",
]
