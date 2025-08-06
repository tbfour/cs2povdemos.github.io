# src/hltv_helpers.py
from hltv_async_api.sync import Hltv          # NEW
hltv = Hltv()                                 # lightweight; 1-2 requests

def get_team(player_name: str) -> str | None:
    """
    Return the player’s current team or None if not found.
    We cache the Hltv() object so the Action does at most one
    network call per player per run.
    """
    try:
        matches = hltv.search_players(player_name, size=1)
        return matches[0]["team"]["name"] if matches else None
    except Exception:
        return None
