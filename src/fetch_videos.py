"""
Rebuild docs/data/videos.json for your CS2 POV site.

• Fetch HLTV top-team ranking (eupeutro API) → build whitelist (nick → team).
• Scan uploads on specified YouTube channels (last 18 months).
• Exclude YouTube Shorts:
    – duration <= 60s OR title contains "#shorts" (case-insensitive).
• Assign player if a whitelist nickname is in the title.
• Keep player in dropdown only if they appear in ≥ MIN_VIDEOS.
• Write newest-first to docs/data/videos.json.
"""

from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
from collections import Counter
import datetime as dt
import json, os, re, requests

# ── Config ──────────────────────────────────────────────────────────────
YT_KEY = os.getenv("YT_API_KEY")
if not YT_KEY:
    raise RuntimeError("YT_API_KEY not set")

CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

CUTOFF      = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=18 * 30)
MIN_VIDEOS  = 10                      # threshold for showing a player in dropdown
SHORTS_MAXS = 60                      # seconds; ≤ 60s treated as Shorts

MAPS = {"mirage","inferno","nuke","ancient","anubis","vertigo","overpass","dust2"}
BLACKLIST = MAPS | {"faceit","pov","demo","highlights","highlight","ranked","cs2","vs","clutch"}
TOKEN = re.compile(r"[A-Za-z0-9_\-]{3,16}")

HLTV_API_BASE = "https://hltv-api.onrender.com/api"

# ── HLTV whitelist (players on top teams) ───────────────────────────────
def fetch_top_players() -> tuple[set[str], dict[str,str]]:
    """
    Returns (whitelist, nick_to_team) using HLTV team rankings.
    """
    url = f"{HLTV_API_BASE}/ranking?type=team&offset=0"
    try:
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        data = resp.json()["data"]

        whitelist: set[str] = set()
        nick_to_team: dict[str, str] = {}

        for team in data:
            team_name = team.get("teamName") or team.get("name") or "unknown"
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

def walk_pl_pages(y, pl_id: str):
    """Yield one page (list of items) at a time to batch-fetch details."""
    tok = None
    while True:
        r = y.playlistItems().list(playlistId=pl_id, part="snippet",
                                   maxResults=50, pageToken=tok).execute()
        items = r["items"]
        if items:
            yield items
        tok = r.get("nextPageToken")
        if not tok:
            break

# ISO 8601 PT#H#M#S → seconds
def duration_to_seconds(iso_dur: str) -> int:
    # Simple parser: extract hours, minutes, seconds
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_dur)
    if not m: return 0
    h = int(m.group(1) or 0)
    m_ = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h*3600 + m_*60 + s

def fetch_durations(y, ids: list[str]) -> dict[str,int]:
    """Return {videoId: seconds} for up to 50 ids per call."""
    out: dict[str,int] = {}
    if not ids:
        return out
    resp = y.videos().list(id=",".join(ids), part="contentDetails").execute()
    for it in resp.get("items", []):
        vid = it["id"]
        dur = it["contentDetails"]["duration"]
        out[vid] = duration_to_seconds(dur)
    return out

# ── Main routine ────────────────────────────────────────────────────────
def main() -> None:
    whitelist, nick_to_team = fetch_top_players()
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

        for page in walk_pl_pages(yt, upl):
            # Batch fetch durations for this page
            ids = [it["snippet"]["resourceId"]["videoId"] for it in page]
            durations = fetch_durations(yt, ids)

            for it in page:
                vid = it["snippet"]["resourceId"]["videoId"]
                pub = isoparse(it["snippet"]["publishedAt"])
                if pub < CUTOFF:
                    continue

                title = it["snippet"]["title"]
                # Shorts filter: explicit tag or short duration
                if "#shorts" in title.lower() or durations.get(vid, 0) <= SHORTS_MAXS:
                    continue

                tokens = TOKEN.findall(title)
                nick = next((t for t in tokens
                            if t.lower() in whitelist_lc and t.lower() not in BLACKLIST),
                            None)
                if nick:
                    counter[nick] += 1

                lower = title.lower()
                game_map = next((m for m in MAPS if m in lower), None)

                vids.append({
                    "id": vid,
                    "title": title,
                    "channel": label,
                    "player": nick,
                    "team": nick_to_team.get(nick),
                    "map": game_map,
                    "published": pub.isoformat()[:10],
                })

    # Keep only players who appear in ≥ MIN_VIDEOS; null others
    keep = {p for p, n in counter.items() if n >= MIN_VIDEOS}
    for v in vids:
        if v["player"] not in keep:
            v["player"] = v["team"] = None

    vids.sort(key=lambda v: v["published"], reverse=True)

    out_dir = Path("docs/data")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "videos.json").write_text(json.dumps(vids, indent=2))
    print(f"[info] wrote {len(vids)} videos "
          f"({len(keep)} players in dropdown)")

if __name__ == "__main__":
    main()
