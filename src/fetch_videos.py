"""
Build data/videos.json for your CS2 POV library.

Workflow
--------
1. Use `cs_rankings.HLTVRankings()` to fetch the current HLTV Top-50 team
   ranking (1 request; no Cloudflare scraping).
2. Extract every roster nickname → whitelist  (and remember each
   nickname’s team name).
3. Scan YouTube uploads on the configured channels (last 18 months).
4. A video’s `player` field is set to the first whitelist nickname that
   appears in its title (case-insensitive exact match).  If no nickname
   appears, player/team stay **None** but the video is still kept.
5. A nickname must occur in **≥ 10** videos to reach the dropdown;
   others are nulled out.
6. Result is written to `data/videos.json`, newest-first.

You only need to:
• `pip install cs_rankings`  (or add to your `Pipfile`)
• make sure `YT_API_KEY` is supplied in the workflow step that runs this
  script.
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
from collections import Counter
import datetime as dt
import json, os, re

from cs_rankings import HLTVRankings   # <— new dependency

# ────────────────────────────── Config ──────────────────────────────────
YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not set")

CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

CUTOFF = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=18 * 30)

MAPS = {
    "mirage", "inferno", "nuke", "ancient", "anubis",
    "vertigo", "overpass", "dust2"
}

BLACKLIST = MAPS | {
    "faceit", "pov", "demo", "highlights", "highlight", "ranked",
    "cs2", "vs", "clutch"
}

TOKEN = re.compile(r"[A-Za-z0-9_\-]{3,16}")

# ────────────────── Step 1: build whitelist from HLTV ───────────────────
def get_whitelist() -> tuple[set[str], dict[str, str]]:
    """Return (whitelist, nickname→team) from HLTV top-50 teams."""
    client = HLTVRankings()
    ranking = client.get_ranking(max_rank=50)     # one API call
    client.close()

    names: set[str] = set()
    nick_to_team: dict[str, str] = {}

    for team in ranking:
        team_name = team["name"]
        for entry in team["players"]:
            nick = entry   # HLTVRankings returns plain nicks in 'players'
            names.add(nick)
            nick_to_team[nick] = team_name
    return names, nick_to_team

# ──────────────── YouTube helper functions (unchanged) ─────────────────
def resolve_channel_id(yapi, handle_or_id: str) -> str | None:
    if handle_or_id.startswith("UC"):
        return handle_or_id
    res = yapi.search().list(
        q=handle_or_id.lstrip("@"), type="channel",
        part="snippet", maxResults=1
    ).execute()
    return res["items"][0]["id"]["channelId"] if res["items"] else None


def upload_playlist_id(yapi, channel_id: str) -> str | None:
    cd = yapi.channels().list(
        id=channel_id, part="contentDetails"
    ).execute()
    if cd["items"]:
        return cd["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return None


def scan_channel(yapi, upl_id: str):
    token = None
    while True:
        res = yapi.playlistItems().list(
            playlistId=upl_id, part="snippet",
            maxResults=50, pageToken=token
        ).execute()
        yield from res["items"]
        token = res.get("nextPageToken")
        if not token:
            break

# ──────────────────────────── Main routine ─────────────────────────────
def main() -> None:
    whitelist, nick_to_team = get_whitelist()
    whitelist_lc = {n.lower() for n in whitelist}

    youtube = build("youtube", "v3", developerKey=YT_KEY)
    videos: list[dict] = []
    counter: Counter[str] = Counter()

    for label, raw in CHANNELS.items():
        cid = resolve_channel_id(youtube, raw)
        if not cid:
            print(f"[warn] cannot resolve {raw!r}")
            continue
        upl = upload_playlist_id(youtube, cid)
        if not upl:
            print(f"[warn] no uploads playlist for {cid}")
            continue

        for item in scan_channel(youtube, upl):
            published = isoparse(item["snippet"]["publishedAt"])
            if published < CUTOFF:
                continue

            title = item["snippet"]["title"]
            tokens = TOKEN.findall(title)
            nick = next((t for t in tokens
                         if t.lower() in whitelist_lc
                         and t.lower() not in BLACKLIST),
                        None)

            if nick:
                counter[nick] += 1

            lower = title.lower()
            game_map = next((m for m in MAPS if m in lower), None)

            videos.append({
                "id": item["snippet"]["resourceId"]["videoId"],
                "title": title,
                "channel": label,
                "player": nick,
                "team": nick_to_team.get(nick),
                "map": game_map,
                "published": published.isoformat()[:10],
            })

    # keep only players who appear in ≥10 videos
    keep = {p for p, n in counter.items() if n >= 10}
    for vid in videos:
        if vid["player"] not in keep:
            vid["player"] = vid["team"] = None

    videos.sort(key=lambda v: v["published"], reverse=True)

    Path("data").mkdir(exist_ok=True)
    Path("data/videos.json").write_text(json.dumps(videos, indent=2))
    print(f"[info] wrote {len(videos)} videos "
          f"({len(keep)} players in dropdown)")

if __name__ == "__main__":
    main()
