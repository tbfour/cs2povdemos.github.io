"""
Build catalogue for POV videos featuring players on HLTV top teams.

• Pull current top-team ranking from eupeutro's hltv-api
• Extract every player nickname into a whitelist (cached 24 h)
• Keep YouTube videos whose title contains a whitelist nickname
• A nickname must appear in ≥10 videos (18-month window) to reach dropdown
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
from collections import Counter
import datetime as dt
import json, os, re, asyncio, requests

from hltv_async_api import Hltv   # only for nickname→team lookup

# ── config ──────────────────────────────────────────────────────────────
YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not set")

CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

CUTOFF = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=18 * 30)

MAPS = {"mirage","inferno","nuke","ancient","anubis",
        "vertigo","overpass","dust2"}

BLACKLIST = MAPS | {
    "faceit","pov","demo","highlights","highlight",
    "ranked","cs2","vs","clutch"
}
TOKEN = re.compile(r"[A-Za-z0-9_\-]{3,16}")

# change this if you self-host the API
API_BASE = "https://hltv-api.onrender.com/api"

# ── fetch & cache whitelist ─────────────────────────────────────────────
WL_FILE = Path("data/whitelist.json")

def fetch_whitelist_live() -> set[str]:
    try:
        url = f"{API_BASE}/ranking?type=team&offset=0"
        teams = requests.get(url, timeout=10).json()["data"]
        names = {p["playerName"]
                 for team in teams
                 for p in team["ranking"]}
        return names
    except Exception as e:
        print(f"[warn] HLTV-API fetch failed: {e}")
        return set()

def get_whitelist() -> set[str]:
    live = fetch_whitelist_live()
    if live:
        WL_FILE.parent.mkdir(exist_ok=True)
        WL_FILE.write_text(json.dumps(sorted(live)))
        return live
    if WL_FILE.exists():
        print("[info] using cached whitelist.json")
        return set(json.loads(WL_FILE.read_text()))
    print("[warn] no whitelist available; player dropdown will be empty")
    return set()

# ── HLTV nickname→team lookup (cached) ──────────────────────────────────
_cache: dict[str, tuple[str,str] | None] = {}

async def _hltv_lookup(tag):
    async with Hltv(timeout=2) as api:
        res = await api.search_players(tag, size=1)
        if res:
            return res[0]["name"], res[0]["team"]["name"]
        return None

def first_valid_player(tokens, whitelist_lc):
    for tok in tokens:
        lo = tok.lower()
        if lo in BLACKLIST or lo not in whitelist_lc:
            continue
        if tok not in _cache:
            try:
                _cache[tok] = asyncio.run(_hltv_lookup(tok))
            except Exception:
                _cache[tok] = None
        return _cache[tok]
    return None

# ── YouTube helpers ─────────────────────────────────────────────────────
def chan_id(y, handle):
    if handle.startswith("UC"):
        return handle
    r = y.search().list(q=handle.lstrip("@"), type="channel",
                        part="snippet", maxResults=1).execute()
    return r["items"][0]["id"]["channelId"] if r["items"] else None

def uploads_pl(y, cid):
    r = y.channels().list(id=cid, part="contentDetails").execute()
    if r["items"]:
        return r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

def walk_pl(y, pl):
    tok = None
    while True:
        r = y.playlistItems().list(playlistId=pl, part="snippet",
                                   maxResults=50, pageToken=tok).execute()
        yield from r["items"]
        tok = r.get("nextPageToken")
        if not tok: break

# ── main ────────────────────────────────────────────────────────────────
def main():
    whitelist = get_whitelist()
    whitelist_lc = {n.lower() for n in whitelist}

    yt = build("youtube","v3",developerKey=YT_KEY)
    vids, counter = [], Counter()

    for label, raw in CHANNELS.items():
        cid = chan_id(yt, raw)
        if not cid: continue
        upl = uploads_pl(yt, cid)
        if not upl: continue

        for it in walk_pl(yt, upl):
            pub = isoparse(it["snippet"]["publishedAt"])
            if pub < CUTOFF: continue

            title = it["snippet"]["title"]
            tokens = TOKEN.findall(title)
            hit = first_valid_player(tokens, whitelist_lc)

            player = team = None
            if hit:
                player, team = hit
                counter[player] += 1

            lower = title.lower()
            game_map = next((m for m in MAPS if m in lower), None)

            vids.append({
                "id": it["snippet"]["resourceId"]["videoId"],
                "title": title,
                "channel": label,
                "player": player,
                "team": team,
                "map": game_map,
                "published": pub.isoformat()[:10],
            })

    keep = {p for p,n in counter.items() if n >= 10}
    for v in vids:
        if v["player"] not in keep:
            v["player"] = v["team"] = None

    vids.sort(key=lambda v: v["published"], reverse=True)
    Path("data").mkdir(exist_ok=True)
    Path("data/videos.json").write_text(json.dumps(vids, indent=2))

if __name__ == "__main__":
    main()
