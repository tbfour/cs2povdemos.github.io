"""
Rebuild docs/data/videos.json for your CS2 POV site.

• Fetch top-team ranking from eupeutro’s HLTV API.
• Build a whitelist of player nicknames and a nick→team map.
• Scan uploads on the configured YouTube channels (last 18 months).
• Set `player` only if a whitelist nickname appears in the title.
• A nickname must appear in ≥10 videos to reach the dropdown.
• Output written to docs/data/videos.json (newest first).
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
from collections import Counter
import datetime as dt
import json, os, re, requests

# ── Secrets & channels ──────────────────────────────────────────────────
YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not set")

CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

# 18-month cutoff (timezone-aware)
CUTOFF = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=18 * 30)

MAPS = {"mirage","inferno","nuke","ancient","anubis","vertigo","overpass","dust2"}

# Words we ignore when scanning tokens for a nickname
BLACKLIST = MAPS | {"faceit","pov","demo","highlights","highlight","ranked","cs2","vs","clutch"}

TOKEN = re.compile(r"[A-Za-z0-9_\-]{3,16}")

# HLTV API base (eupeutro). Change if you self-host.
API_BASE = "https://hltv-api.onrender.com/api"

# ── Build whitelist from ranking ────────────────────────────────────────
def fetch_top_players() -> tuple[set[str], dict[str,str]]:
    """
    Returns (whitelist, nick_to_team) using HLTV team rankings.
    """
    url = f"{API_BASE}/ranking?type=team&offset=0"
    try:
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        data = resp.json()["data"]

        whitelist: set[str] = set()
        nick_to_team: dict[str, str] = {}

        for team in data:
            team_name = team.get("teamName") or team.get("name")
            for p in team["ranking"]:
                nick = p["playerName"]
                whitelist.add(nick)
                nick_to_team[nick] = team_name
        return whitelist, nick_to_team
    except Exception as e:
        print(f"[warn] HLTV API fetch failed: {e}")
        return set(), {}

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
    tok = None
    while True:
        r = y.playlistItems().list(playlistId=pl_id, part="snippet",
                                   maxResults=50, pageToken=tok).execute()
        yield from r["items"]
        tok = r.get("nextPageToken")
        if not tok:
            break

# ── Main routine ────────────────────────────────────────────────────────
def main() -> None:
    whitelist, nick_to_team = fetch_top_players()
    whitelist_lc = {n.lower() for n in whitelist}

    yt = build("youtube", "v3", developerKey=YT_KEY)
    vids: list[dict] = []
    counter: Counter[str] = Counter()

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

            # first token that is a whitelist nickname and not a blacklist word
            nick = next((t for t in tokens
                         if t.lower() in whitelist_lc and t.lower() not in BLACKLIST),
                        None)

            if nick:
                counter[nick] += 1

            lower = title.lower()
            game_map = next((m for m in MAPS if m in lower), None)

            vids.append({
                "id": it["snippet"]["resourceId"]["videoId"],
                "title": title,
                "channel": label,
                "player": nick,
                "team": nick_to_team.get(nick),
                "map": game_map,
                "published": pub.isoformat()[:10],
            })

    # Only keep players who appear often enough for a dropdown entry
    keep = {p for p, n in counter.items() if n >= 10}
    for v in vids:
        if v["player"] not in keep:
            v["player"] = v["team"] = None

    vids.sort(key=lambda v: v["published"], reverse=True)

    out_dir = Path("docs/data")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "videos.json").write_text(json.dumps(vids, indent=2))
    print(f"[info] wrote {len(vids)} videos ({len(keep)} players in dropdown)")

if __name__ == "__main__":
    main()
