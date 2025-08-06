"""
Build a catalogue of recent CS2 POV videos.

• Scans specific YouTube channels (last 18 months)
• Extracts player + map from titles
• Canonicalises player names via HLTV and keeps only videos whose
  player resolves to a current team
• Stores original title for front-end display
• Keeps only players that appear ≥ 5 times in the 18-month window
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
from collections import Counter
import datetime as dt
import json, os, re, asyncio

from hltv_async_api import Hltv     # async HLTV wrapper

# ── Config ------------------------------------------------------------------
YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not set")

CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

CUTOFF = dt.datetime.utcnow() - dt.timedelta(days=18 * 30)   # ≈ 18 months

MAPS = {"mirage", "inferno", "nuke", "ancient", "anubis",
        "vertigo", "overpass", "dust2"}

PLAYER_RE = re.compile(r"[A-Za-z0-9_\-]{3,16}")

# ── YouTube helpers ----------------------------------------------------------
def resolve_channel_id(y, handle_or_id: str) -> str | None:
    if handle_or_id.startswith("UC"):
        return handle_or_id
    res = y.search().list(q=handle_or_id.lstrip("@"), type="channel",
                          part="snippet", maxResults=1).execute()
    return res["items"][0]["id"]["channelId"] if res["items"] else None


def get_upload_playlist_id(y, cid: str) -> str | None:
    cd = y.channels().list(id=cid, part="contentDetails").execute()
    if cd["items"]:
        return cd["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return None


def scan_channel(y, upl_id: str):
    items, token = [], None
    while True:
        res = y.playlistItems().list(playlistId=upl_id, part="snippet",
                                     maxResults=50, pageToken=token).execute()
        items.extend(res["items"])
        token = res.get("nextPageToken")
        if not token:
            break
    return items

# ── Title parsing & canonicalisation ----------------------------------------
def parse_title(title: str) -> tuple[str | None, str | None]:
    lower = title.lower()
    map_hit = next((m for m in MAPS if m in lower), None)
    cleaned = re.sub(r"(pov|demo|highlights|vs|/|\\)", " ",
                     title, flags=re.I)
    m = PLAYER_RE.search(cleaned)
    player = m.group(0) if m else None
    return player, map_hit


async def _hltv_canon(raw: str) -> tuple[str | None, str | None]:
    """Return (nick, team) or (None, None) if HLTV can’t find the player."""
    async with Hltv(timeout=2) as api:
        res = await api.search_players(raw, size=1)
        if res:
            nick = res[0]["name"]
            team = res[0]["team"]["name"]
            return nick, team
        return None, None


def canonicalise_and_team(raw: str) -> tuple[str | None, str | None]:
    try:
        nick, team = asyncio.run(_hltv_canon(raw))
        if nick and team:
            return nick, team
    except Exception:
        pass
    return None, None   # discard if HLTV has no info

# ── Main routine ------------------------------------------------------------
def main() -> None:
    y = build("youtube", "v3", developerKey=YT_KEY)

    out = Path("data/videos.json")
    existing = []                      # always rebuild fresh now

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

            title = item["snippet"]["title"]
            player_raw, game_map = parse_title(title)
            if not player_raw:
                continue

            player, team = canonicalise_and_team(player_raw)
            if not player:             # skip unknown / free-agent players
                continue

            player_counter[player] += 1

            existing.append({
                "id": item["snippet"]["resourceId"]["videoId"],
                "title": title,           # original YouTube title
                "channel": label,
                "player": player,
                "team": team,
                "map": game_map,
                "published": pub_date.isoformat()[:10],
            })

    # keep players that appear ≥ 5 times
    whitelist = {p for p, n in player_counter.items() if n >= 5}
    existing = [v for v in existing if v["player"] in whitelist]

    existing.sort(key=lambda v: v["published"], reverse=True)
    Path("data").mkdir(exist_ok=True)
    out.write_text(json.dumps(existing, indent=2))

if __name__ == "__main__":
    main()
