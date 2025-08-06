from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
import json, os, re, datetime as dt
import asyncio
from hltv_async_api import Hltv 

YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not found in env")

# ─── YouTube helpers ──────────────────────────────────────────────────────────
CHANNELS = {                        # you can keep handles *or* raw IDs here
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

def resolve_channel_id(y, handle_or_id: str) -> str | None:
    """Turn a handle like '@lim-csgopov' into a UC-style channel ID."""
    if handle_or_id.startswith("UC"):            # already an ID
        return handle_or_id
    res = y.search().list(
        q=handle_or_id.lstrip("@"), type="channel",
        part="snippet", maxResults=1
    ).execute()
    if res["items"]:
        return res["items"][0]["id"]["channelId"]
    return None

def get_upload_playlist_id(y, channel_id: str) -> str | None:
    cd = y.channels().list(id=channel_id, part="contentDetails").execute()
    if cd["items"]:
        return cd["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return None
# ──────────────────────────────────────────────────────────────────────────────

def scan_channel(y, upload_pl):
    vids, nextp = [], None
    while True:
        res = y.playlistItems().list(
            playlistId=upload_pl, part="snippet", maxResults=50,
            pageToken=nextp
        ).execute()
        vids.extend(res["items"])
        nextp = res.get("nextPageToken")
        if not nextp: break
    return vids

# ── CS2 map list used by the title parser ────────────────────────────────────
MAPS = {
    "mirage",
    "inferno",
    "nuke",
    "ancient",
    "anubis",
    "vertigo",
    "overpass",
    "dust2",
}
# ─────────────────────────────────────────────────────────────────────────────

def parse_title(t: str) -> tuple[str, str | None]:
    """
    Very simple heuristic:
      • player  = first token before '-', '|', or 'vs'
      • map_hit = first known map substring found in lowercase title
    """
    t_low = t.lower()
    map_hit = next((m for m in MAPS if m in t_low), None)
    player = re.split(r"[-|]|vs", t, maxsplit=1)[0].strip()
    return player, map_hit

# --- HLTV lookup ----------------------------------------------------------
_team_cache: dict[str, str | None] = {}

async def _lookup(player: str) -> str | None:
    async with Hltv(timeout=2, max_delay=1) as api:
        res = await api.search_players(player, size=1)
        return res[0]["team"]["name"] if res else None

def enrich_player(player: str) -> str | None:
    if player in _team_cache:                # hit the in-memory cache
        return _team_cache[player]
    try:
        team = asyncio.run(_lookup(player))  # run the coroutine
    except Exception:
        team = None
    _team_cache[player] = team               # memoise
    return team
# --------------------------------------------------------------------------

def main() -> None:
    y = build("youtube", "v3", developerKey=YT_KEY)

    # load existing catalogue (if any)
    existing_path = Path("data/videos.json")
    existing = json.loads(existing_path.read_text()) if existing_path.exists() else []
    ids_seen = {v["id"] for v in existing}

    for label, raw_channel in CHANNELS.items():
        cid = resolve_channel_id(y, raw_channel)
        if not cid:
            print(f"[warn] could not resolve channel {raw_channel!r} – skipping")
            continue

        upl = get_upload_playlist_id(y, cid)
        if not upl:
            print(f"[warn] no uploads playlist for channel {cid} – skipping")
            continue

        for item in scan_channel(y, upl):
            vid = item["snippet"]["resourceId"]["videoId"]
            if vid in ids_seen:
                continue

            title = item["snippet"]["title"]
            player, gmap = parse_title(title)
            team = enrich_player(player)

            existing.append(
                {
                    "id": vid,
                    "title": title,
                    "channel": label,
                    "player": player,
                    "team": team,
                    "map": gmap,
                    "published": item["snippet"]["publishedAt"][:10],
                }
            )
            ids_seen.add(vid)

    # sort newest → oldest
    existing.sort(key=lambda v: isoparse(v["published"]), reverse=True)

    Path("data").mkdir(exist_ok=True)
    existing_path.write_text(json.dumps(existing, indent=2))

if __name__ == "__main__":
    main()
