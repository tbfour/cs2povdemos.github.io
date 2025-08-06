"""
Rebuild data/videos.json for your CS2 POV site.

• Pull the current top team ranking from eupeutro’s HLTV API.
• Build a whitelist of player nicknames and remember each nickname’s team.
• Scan uploads on the configured YouTube channels (last 18 months).
• A video’s player field is set only if its title contains a whitelist nickname.
  Videos without a pro name are still kept, but player/team remain None.
• A nickname must appear in ≥10 videos in the window to reach the dropdown.
• Output written to docs/data/videos.json (newest first).
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
from collections import Counter
import datetime as dt
import json, os, re, requests, asyncio

from hltv_async_api import Hltv  # for nickname → team lookup

# ── secrets & channels ──────────────────────────────────────────────────
YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not set")

CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

# 18‑month cutoff (timezone-aware to avoid TypeError)
CUTOFF = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=18 * 30)

MAPS = {"mirage","inferno","nuke","ancient","anubis",
        "vertigo","overpass","dust2"}

BLACKLIST = MAPS | {
    "faceit","pov","demo","highlights","highlight","ranked",
    "cs2","vs","clutch"
}

TOKEN = re.compile(r"[A-Za-z0-9_\-]{3,16}")

# Endpoint for eupeutro’s HLTV API (change if self-hosting)
API_BASE = "https://hltv-api.onrender.com/api"

# ── fetch & cache whitelist ─────────────────────────────────────────────
WL_FILE = Path("docs/data/whitelist.json")

def fetch_whitelist_live() -> set[str]:
    """
    Pull top team ranking from the HLTV API and extract all player names.
    """
    try:
        url = f"{API_BASE}/ranking?type=team&offset=0"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        teams = response.json()["data"]
        names = {p["playerName"] for team in teams for p in team["ranking"]}
        return names
    except Exception as e:
        print(f"[warn] HLTV API fetch failed: {e}")
        return set()

def get_whitelist() -> set[str]:
    """
    Return the current whitelist. Use cached whitelist.json if API fails.
    """
    live = fetch_whitelist_live()
    if live:
        WL_FILE.parent.mkdir(parents=True, exist_ok=True)
        WL_FILE.write_text(json.dumps(sorted(live)))
        return live
    if WL_FILE.exists():
        print("[info] using cached whitelist")
        return set(json.loads(WL_FILE.read_text()))
    print("[warn] no whitelist available; player dropdown will be empty")
    return set()

# ── HLTV nickname→team lookup (cached) ──────────────────────────────────
_cache: dict[str, tuple[str,str] | None] = {}

async def _hltv_lookup(tag: str) -> tuple[str,str] | None:
    async with Hltv(timeout=2) as api:
        res = await api.search_players(tag, size=1)
        if res:
            nick = res[0]["name"]
            team = res[0]["team"]["name"]
            return nick, team
        return None

def first_valid_player(tokens: list[str], whitelist_lc: set[str]) -> tuple[str,str] | None:
    """
    Return (nickname, team) if a token is on the whitelist and resolves via HLTV.
    """
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
def chan_id(y, handle_or_id: str) -> str | None:
    if handle_or_id.startswith("UC"):
        return handle_or_id
    r = y.search().list(q=handle_or_id.lstrip("@"), type="channel",
                        part="snippet", maxResults=1).execute()
    return r["items"][0]["id"]["channelId"] if r["items"] else None

def uploads_pl(y, cid: str) -> str | None:
    r = y.channels().list(id=cid, part="contentDetails").execute()
    if r["items"]:
        return r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

def walk_pl(y, pl_id: str):
    token = None
    while True:
        r = y.playlistItems().list(playlistId=pl_id, part="snippet",
                                   maxResults=50, pageToken=token).execute()
        yield from r["items"]
        token = r.get("nextPageToken")
        if not token:
            break

# ── main routine ────────────────────────────────────────────────────────
def main() -> None:
    whitelist = get_whitelist()
    whitelist_lc = {n.lower() for n in whitelist}

    yt = build("youtube", "v3", developerKey=YT_KEY)
    vids, counter = [], Counter()

    for label, raw in CHANNELS.items():
        cid = chan_id(yt, raw)
        if not cid:
            print(f"[warn] cannot resolve {raw!r}")
            continue
        upl = uploads_pl(yt, cid)
        if not upl:
            print(f"[warn] no uploads playlist for {cid}")
            continue

        for it in walk_pl(yt, upl):
            pub = isoparse(it["snippet"]["publishedAt"])
            if pub < CUTOFF:
                continue

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

    # keep only players appearing in ≥10 videos
    keep = {p for p, n in counter.items() if n >= 10}
    for v in vids:
        if v["player"] not in keep:
            v["player"] = v["team"] = None

    vids.sort(key=lambda v: v["published"], reverse=True)

    # Write JSON into docs/data/ (ensure folder exists)
    out_dir = Path("docs/data")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "videos.json").write_text(json.dumps(vids, indent=2))
    print(f"[info] wrote {len(vids)} videos ({len(keep)} players in dropdown)")

if __name__ == "__main__":
    main()
