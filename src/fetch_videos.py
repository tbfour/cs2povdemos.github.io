"""
Build catalogue of POV videos strictly for HLTV top-50 pros.

Pipeline:
• Get Top-50 teams from HLTV -> roster -> whitelist of nicknames
• Scan uploads on selected channels (last 18 months)
• Keep video if its title contains any whitelist nickname (case-insensitive)
• Player must appear in ≥10 videos to reach dropdown
• JSON written to data/videos.json
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
from collections import Counter
import datetime as dt
import json, os, re, asyncio

from hltv_async_api import Hltv

# ── Secrets & channels ──────────────────────────────────────────────────
YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not set")

CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

CUTOFF = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=18 * 30)  # 18 mo
MAPS = {"mirage","inferno","nuke","ancient","anubis",
        "vertigo","overpass","dust2"}

TOKEN = re.compile(r"[A-Za-z0-9_\-]{3,16}")

# ── HLTV helpers ---------------------------------------------------------
async def top50_pros() -> set[str]:
    """Return a set of nicknames for players on HLTV top-50 teams."""
    async with Hltv(timeout=4) as api:
        teams = await api.get_top_teams(50)
        whitelist = set()
        for t in teams:
            roster = await api.get_team(t["id"])
            for p in roster["players"]:
                whitelist.add(p["name"])
        return whitelist

def get_whitelist() -> set[str]:
    # Simple local cache (data/whitelist.json) so we don’t ping HLTV every run
    cache = Path("data/whitelist.json")
    if cache.exists() and (dt.datetime.now(dt.timezone.utc) -
                           dt.datetime.fromtimestamp(cache.stat().st_mtime,
                                                      dt.timezone.utc)
                           ).days < 1:
        return set(json.loads(cache.read_text()))
    wl = asyncio.run(top50_pros())
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(sorted(wl)))
    return wl

# ── YouTube helpers ------------------------------------------------------
def channel_id(y, h_or_id):
    if h_or_id.startswith("UC"):
        return h_or_id
    r = y.search().list(q=h_or_id.lstrip("@"), type="channel",
                        part="snippet", maxResults=1).execute()
    return r["items"][0]["id"]["channelId"] if r["items"] else None

def uploads_pl(y, cid):
    r = y.channels().list(id=cid, part="contentDetails").execute()
    if r["items"]:
        return r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

def playlist_items(y, pl):
    tok = None
    while True:
        r = y.playlistItems().list(playlistId=pl, part="snippet",
                                   maxResults=50, pageToken=tok).execute()
        yield from r["items"]
        tok = r.get("nextPageToken")
        if not tok: break

# ── Build catalogue ------------------------------------------------------
def main():
    whitelist = get_whitelist()
    whitelist_lc = {n.lower() for n in whitelist}

    yt = build("youtube","v3",developerKey=YT_KEY)
    vids, counter = [], Counter()

    for label, raw in CHANNELS.items():
        cid = channel_id(yt, raw)
        if not cid: continue
        upl = uploads_pl(yt, cid)
        if not upl: continue

        for it in playlist_items(yt, upl):
            pub = isoparse(it["snippet"]["publishedAt"])
            if pub < CUTOFF: continue

            title = it["snippet"]["title"]
            tokens = TOKEN.findall(title)
            nick = next((t for t in tokens if t.lower() in whitelist_lc), None)

            if nick:
                counter[nick] += 1

            lower = title.lower()
            game_map = next((m for m in MAPS if m in lower), None)

            vids.append({
                "id"   : it["snippet"]["resourceId"]["videoId"],
                "title": title,
                "channel": label,
                "player": nick,                       # may be None
                "map": game_map,
                "published": pub.isoformat()[:10],
            })

    # keep only players with ≥10 videos
    keep = {p for p,n in counter.items() if n >= 10}
    for v in vids:
        if v["player"] not in keep:
            v["player"] = None

    vids.sort(key=lambda v: v["published"], reverse=True)

    Path("data").mkdir(exist_ok=True)
    Path("data/videos.json").write_text(json.dumps(vids, indent=2))

if __name__ == "__main__":
    main()
