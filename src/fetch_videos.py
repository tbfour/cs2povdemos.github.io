"""
Fetch recent CS2 POV videos from selected channels, enrich with HLTV data,
and write a JSON catalogue (last 18 months, players w/ ≥5 mentions).
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
from collections import Counter
import datetime as dt
import json, os, re, asyncio

from hltv_async_api import Hltv  # async client

# ── YouTube + API key ────────────────────────────────────────────────────────
YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not found in env")

# Channel handles or UC-IDs
CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

# ── Cutoff & constants ───────────────────────────────────────────────────────
CUTOFF = dt.datetime.utcnow() - dt.timedelta(days=18 * 30)  # ≈ 18 months

MAPS = {"mirage", "inferno", "nuke", "ancient", "anubis",
        "vertigo", "overpass", "dust2"}

PLAYER_RE = re.compile(r"[A-Za-z0-9_\-]{3,16}")

# ── Helpers ──────────────────────────────────────────────────────────────────
def resolve_channel_id(y, handle_or_id: str) -> str | None:
    if handle_or_id.startswith("UC"):
        return handle_or_id
    res = y.search().list(q=handle_or_id.lstrip("@"), type="channel",
                          part="snippet", maxResults=1).execute()
    return res["items"][0]["id"]["channelId"] if res["items"] else None

def get_upload_playlist_id(y, channel_id: str) -> str | None:
    cd = y.channels().list(id=channel_id,
                           part="contentDetails").execute()
    if cd["items"]:
        return cd["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return None

def scan_channel(y, upload_pl: str):
    vids, nextp = [], None
    while True:
        res = y.playlistItems().list(playlistId=upload_pl, part="snippet",
                                     maxResults=50, pageToken=nextp).execute()
        vids.extend(res["items"])
        nextp = res.get("nextPageToken")
        if not nextp:
            break
    return vids

def parse_title(title: str) -> tuple[str | None, str | None]:
    lower = title.lower()
    map_hit = next((m for m in MAPS if m in lower), None)
    cleaned = re.sub(r"(pov|demo|highlights|vs|/|\\)", " ", title, flags=re.I)
    m = PLAYER_RE.search(cleaned)
    player = m.group(0) if m else None
    return player, map_hit

# ── HLTV enrichment (async wrapper with small cache) ─────────────────────────
_team_cache: dict[str, str | None] = {}

async def _lookup(player: str) -> str | None:
    async with Hltv(timeout=2, max_delay=1) as api:
        res = await api.search_players(player, size=1)
        return res[0]["team"]["name"] if res else None

def enrich_player(player: str) -> str | None:
    if player in _team_cache:
        return _team_cache[player]
    try:
        team = asyncio.run(_lookup(player))
    except Exception:
        team = None
    _team_cache[player] = team
    return team

# ── Main routine ─────────────────────────────────────────────────────────────
def main() -> None:
    y = build("youtube", "v3", developerKey=YT_KEY)

    out_path = Path("data/videos.json")
    existing = json.loads(out_path.read_text()) if out_path.exists() else []
    ids_seen = {v["id"] for v in existing}

    player_counter = Counter()

    for label, raw in CHANNELS.items():
        cid = resolve_channel_id(y, raw)
        if not cid:
            print(f"[warn] cannot resolve {raw!r}")
            continue
        upl = get_upload_playlist_id(y, cid)
        if not upl:
            print(f"[warn] no uploads playlist for {cid}")
            continue

        for item in scan_channel(y, upl):
            pub_date = isoparse(item["snippet"]["publishedAt"])
            if pub_date < CUTOFF:
                continue

            vid = item["snippet"]["resourceId"]["videoId"]
            if vid in ids_seen:
                continue

            title = item["snippet"]["title"]
            player, gmap = parse_title(title)
            if player:
                player_counter[player] += 1

            existing.append({
                "id": vid,
                "title": title,
                "channel": label,
                "player": player,
                "team": None,     # filled later
                "map": gmap,
                "published": pub_date.isoformat()[:10],
            })
            ids_seen.add(vid)

    # keep players mentioned ≥5 times
    whitelist = {p for p, n in player_counter.items() if n >= 5}

    for v in existing:
        if v["player"] not in whitelist:
            v["player"] = None
        if v["player"] and v["team"] is None:
            v["team"] = enrich_player(v["player"])

    existing.sort(key=lambda v: v["published"], reverse=True)

    Path("data").mkdir(exist_ok=True)
    out_path.write_text(json.dumps(existing, indent=2))

if __name__ == "__main__":
    main()
