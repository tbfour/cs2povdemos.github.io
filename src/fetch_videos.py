"""
Build clean data/videos.json:

• Scan selected YouTube channels (uploads playlists)
• Last 18 months only
• For each title, scan tokens until HLTV confirms one is a real player
  on a current team
• Keep only players with ≥ 10 videos in that window
• Write list sorted newest → oldest
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from collections import Counter
from pathlib import Path
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

CUTOFF = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=18 * 30)   # ≈ 18 months

MAPS = {"mirage","inferno","nuke","ancient","anubis","vertigo","overpass","dust2"}
BLACKLIST = MAPS | {
    "faceit","pov","demo","highlights","highlight","ranked","cs2","vs","clutch"
}
TOKEN = re.compile(r"[A-Za-z0-9_\-]{3,16}")                  # candidate tags

# ── YouTube helpers ─────────────────────────────────────────────────────
def channel_id(y, handle_or_id: str) -> str | None:
    if handle_or_id.startswith("UC"):
        return handle_or_id
    r = y.search().list(q=handle_or_id.lstrip("@"), type="channel",
                        part="snippet", maxResults=1).execute()
    return r["items"][0]["id"]["channelId"] if r["items"] else None

def uploads_playlist(y, cid: str) -> str | None:
    r = y.channels().list(id=cid, part="contentDetails").execute()
    if r["items"]:
        return r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return None

def playlist_items(y, upl: str):
    tok = None
    while True:
        r = y.playlistItems().list(playlistId=upl, part="snippet",
                                   maxResults=50, pageToken=tok).execute()
        yield from r["items"]
        tok = r.get("nextPageToken")
        if not tok:
            break

# ── HLTV helpers with memo-cache ────────────────────────────────────────
_cache: dict[str, tuple[str, str] | None] = {}

async def _hltv_lookup(tag: str) -> tuple[str, str] | None:
    async with Hltv(timeout=2) as api:
        res = await api.search_players(tag, size=1)
        if res:
            nick = res[0]["name"]
            team = res[0]["team"]["name"]
            return nick, team
        return None

def first_valid_player(tokens: list[str]) -> tuple[str, str] | None:
    for tok in tokens:
        lo = tok.lower()
        if lo in BLACKLIST:
            continue
        if tok in _cache:                    # hit/miss cached
            hit = _cache[tok]
        else:
            try:
                hit = asyncio.run(_hltv_lookup(tok))
            except Exception:
                hit = None
            _cache[tok] = hit
        if hit:
            return hit                       # (nick, team)
    return None

# ── Build catalogue ────────────────────────────────────────────────────
def main() -> None:
    yt = build("youtube", "v3", developerKey=YT_KEY)
    vids, counter = [], Counter()

    for label, raw in CHANNELS.items():
        cid = channel_id(yt, raw)
        if not cid:
            print(f"[warn] can’t resolve {raw}")
            continue
        upl = uploads_playlist(yt, cid)
        if not upl:
            print(f"[warn] no uploads playlist for {cid}")
            continue

        for it in playlist_items(yt, upl):
            pub = isoparse(it["snippet"]["publishedAt"])
            if pub < CUTOFF:
                continue

            title = it["snippet"]["title"]
            tokens = TOKEN.findall(title)
            hit = first_valid_player(tokens)
            if not hit:
                continue                     # skip if no HLTV match
            nick, team = hit

            lower = title.lower()
            game_map = next((m for m in MAPS if m in lower), None)

            vids.append({
                "id": it["snippet"]["resourceId"]["videoId"],
                "title": title,
                "channel": label,
                "player": nick,
                "team": team,
                "map": game_map,
                "published": pub.isoformat()[:10],
            })
            counter[nick] += 1

    # keep players with ≥10 videos
    keep = {p for p, n in counter.items() if n >= 10}
    vids = [v for v in vids if v["player"] in keep]

    vids.sort(key=lambda v: v["published"], reverse=True)
    Path("data").mkdir(exist_ok=True)
    Path("data/videos.json").write_text(json.dumps(vids, indent=2))

if __name__ == "__main__":
    main()
