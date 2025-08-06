"""
Rebuild data/videos.json with clean player names.

• Scans selected YouTube channels (uploads playlists)
• Last 18 months only
• Finds first token in the title that HLTV recognises as a player
• Keeps video only if HLTV returns (nick, current_team)
• Drops players with <5 videos in the window
• Stores the original YouTube title for display
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
from collections import Counter
import datetime as dt
import json, os, re, asyncio

from hltv_async_api import Hltv

# ── Config ──────────────────────────────────────────────────────────────
YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not set")

CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

CUTOFF = dt.datetime.utcnow() - dt.timedelta(days=18 * 30)   # ≈ 18 months

MAPS  = {"mirage","inferno","nuke","ancient","anubis",
         "vertigo","overpass","dust2"}
TOKEN = re.compile(r"[A-Za-z0-9_\-]{3,16}")                  # candidate tags

# ── YouTube helpers ─────────────────────────────────────────────────────
def resolve_channel_id(y, handle_or_id: str) -> str | None:
    if handle_or_id.startswith("UC"):
        return handle_or_id
    res = y.search().list(q=handle_or_id.lstrip("@"), type="channel",
                          part="snippet", maxResults=1).execute()
    return res["items"][0]["id"]["channelId"] if res["items"] else None

def upload_playlist_id(y, cid: str) -> str | None:
    cd = y.channels().list(id=cid, part="contentDetails").execute()
    if cd["items"]:
        return cd["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return None

def playlist_items(y, upl_id: str):
    tok = None
    while True:
        res = y.playlistItems().list(playlistId=upl_id, part="snippet",
                                     maxResults=50, pageToken=tok).execute()
        yield from res["items"]
        tok = res.get("nextPageToken")
        if not tok:
            break

# ── HLTV helpers with caching ───────────────────────────────────────────
_cache: dict[str, tuple[str, str] | None] = {}

async def _lookup(token: str) -> tuple[str, str] | None:
    async with Hltv(timeout=2) as api:
        res = await api.search_players(token, size=1)
        if res:
            nick = res[0]["name"]
            team = res[0]["team"]["name"]
            return nick, team
        return None

def resolve_player(tokens: list[str]) -> tuple[str, str] | None:
    for tok in tokens:
        if tok in _cache:
            hit = _cache[tok]
            if hit:
                return hit
            continue
        try:
            hit = asyncio.run(_lookup(tok))
        except Exception:
            hit = None
        _cache[tok] = hit
        if hit:
            return hit
    return None

# ── Main routine ────────────────────────────────────────────────────────
def main() -> None:
    youtube = build("youtube", "v3", developerKey=YT_KEY)
    videos  = []
    counter = Counter()

    for label, raw in CHANNELS.items():
        cid = resolve_channel_id(youtube, raw)
        if not cid:
            print(f"[warn] cannot resolve {raw!r}")
            continue
        upl = upload_playlist_id(youtube, cid)
        if not upl:
            print(f"[warn] no uploads playlist for {cid}")
            continue

        for it in playlist_items(youtube, upl):
            pub = isoparse(it["snippet"]["publishedAt"])
            if pub < CUTOFF:
                continue

            title = it["snippet"]["title"]
            tokens = TOKEN.findall(title)
            hit    = resolve_player(tokens)
            if not hit:
                continue                        # skip unknown / free-agent
            nick, team = hit

            lower = title.lower()
            game_map = next((m for m in MAPS if m in lower), None)

            videos.append({
                "id": it["snippet"]["resourceId"]["videoId"],
                "title": title,
                "channel": label,
                "player": nick,
                "team": team,
                "map": game_map,
                "published": pub.isoformat()[:10],
            })
            counter[nick] += 1

    # keep players with ≥5 videos
    whitelist = {p for p, n in counter.items() if n >= 5}
    videos = [v for v in videos if v["player"] in whitelist]

    videos.sort(key=lambda v: v["published"], reverse=True)
    Path("data").mkdir(exist_ok=True)
    Path("data/videos.json").write_text(json.dumps(videos, indent=2))

if __name__ == "__main__":
    main()
