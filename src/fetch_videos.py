"""
Rebuild docs/data/videos.json for the CS2 POV site.

POV channels (lim, pov_highlights, nebula):
  • Exclude Shorts (duration ≤ 60 s or "#shorts" in title).
  • Assign player from HLTV whitelist; falls back to title-based extraction.
  • channel field: the channel label ("lim", "pov_highlights", "nebula").

NadesOutHere channel — split into two categories:
  • Long-form → channel: "strategy"
  • Shorts     → channel: "utility"
  • No player detection; map detected from title.

All videos: write newest-first to docs/data/videos.json.
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

# POV channels: shorts are excluded, player detection is active
POV_CHANNELS = {
    "lim":            "@lim-csgopov",
    "pov_highlights": "@CSGOPOVDemosHighlights",
    "nebula":         "@NebulaCS2",
}

# Split channel: long-form → "strategy", shorts → "utility"
NADESOUTHERE = "@NadesOutHere"

CUTOFF      = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=18 * 30)
MIN_VIDEOS  = 10
SHORTS_MAXS = 60

MAPS = {"mirage","inferno","nuke","ancient","anubis","vertigo","overpass","dust2"}
BLACKLIST = MAPS | {"faceit","pov","demo","highlights","highlight","ranked","cs2","vs","clutch"}

# Known CS2 pro team name tokens so the fallback never mistakes a team prefix
# (e.g. "Falcons Niko …") for a player name.
CS2_TEAM_TOKENS = {
    "falcons","vitality","faze","navi","heroic","mouz","ence","liquid",
    "cloud9","spirit","astralis","nip","mibr","complexity","aurora","apeks",
    "imperial","fluxo","fnatic","mongols","mongolz","saw","monte","rebels",
    "grayhound","tyloo","outsiders","gambit","gamerlegion","passion","lynn",
    "big","og","virtus","mousesports","ninjas","pyjamas","col","pain",
    "eternafire","9ine","nine","team","esports","gaming","clan","furia",
}

FALLBACK_STOP_WORDS = BLACKLIST | CS2_TEAM_TOKENS | {
    "ft","with","the","in","on","at","by","for","to","of","and","or",
    "pro","full","best","game","play","win","top","new","live","clip",
    "round","epic","csgo","esea","major","open","cup","lan",
}
TOKEN = re.compile(r"[A-Za-z0-9_\-]{3,16}")

HLTV_API_BASE = "https://hltv-api.onrender.com/api"

# ── HLTV whitelist ───────────────────────────────────────────────────────
def fetch_team_data() -> tuple[set[str], dict[str,str]]:
    """Returns (whitelist, nick_to_team). Handles multiple API response shapes."""
    url = f"{HLTV_API_BASE}/ranking?type=team&offset=0"
    try:
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        raw = resp.json()
        data = raw.get("data", raw) if isinstance(raw, dict) else raw

        whitelist:    set[str]        = set()
        nick_to_team: dict[str, str]  = {}

        for entry in data:
            team_obj  = entry.get("team") or {}
            team_name = (entry.get("teamName") or entry.get("name")
                         or team_obj.get("name") or "unknown")
            players_raw = (entry.get("players") or entry.get("ranking")
                           or entry.get("members") or [])
            for p in players_raw:
                nick = (p.get("name") or p.get("playerName") or p.get("nick"))
                if not nick:
                    continue
                whitelist.add(nick)
                nick_to_team[nick] = team_name

        if not whitelist:
            print(f"[warn] HLTV API returned no players. Sample: {str(raw)[:300]}")
        return whitelist, nick_to_team
    except Exception as e:
        print(f"[warn] HLTV API fetch failed: {e}")
        return set(), {}

def extract_fallback_player(title: str) -> str | None:
    """First title token that looks like a player name when whitelist is unavailable."""
    for tok in TOKEN.findall(title):
        if tok.lower() not in FALLBACK_STOP_WORDS and not tok.isdigit():
            return tok
    return None

# ── YouTube helpers ──────────────────────────────────────────────────────
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
    tok = None
    while True:
        r = y.playlistItems().list(playlistId=pl_id, part="snippet",
                                   maxResults=50, pageToken=tok).execute()
        items = r.get("items", [])
        if items:
            yield items
        if items:
            oldest = min(isoparse(it["snippet"]["publishedAt"]) for it in items)
            if oldest < CUTOFF:
                break
        tok = r.get("nextPageToken")
        if not tok:
            break

def duration_to_seconds(iso_dur: str) -> int:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_dur or "")
    if not m: return 0
    return int(m.group(1) or 0)*3600 + int(m.group(2) or 0)*60 + int(m.group(3) or 0)

def fetch_durations(y, ids: list[str]) -> dict[str,int]:
    out: dict[str,int] = {}
    if not ids:
        return out
    resp = y.videos().list(id=",".join(ids), part="contentDetails").execute()
    for it in resp.get("items", []):
        out[it["id"]] = duration_to_seconds(it["contentDetails"]["duration"])
    return out

def detect_map(title: str) -> str | None:
    normalized = re.sub(r'\bdust\s*2\b', 'dust2', title, flags=re.IGNORECASE)
    lower = normalized.lower()
    return next((m for m in MAPS if m in lower), None)

# ── Main ─────────────────────────────────────────────────────────────────
def main() -> None:
    whitelist, nick_to_team = fetch_team_data()
    whitelist_lc = {n.lower() for n in whitelist}
    canonical    = {n.lower(): n for n in whitelist}  # lower → HLTV canonical casing
    using_fallback = not whitelist_lc
    if using_fallback:
        print("[info] HLTV whitelist empty — using title-based player fallback")

    yt = build("youtube", "v3", developerKey=YT_KEY)
    vids, counter = [], Counter()

    # ── POV channels ──────────────────────────────────────────────────────
    for label, handle in POV_CHANNELS.items():
        cid = chan_id(yt, handle)
        if not cid:
            print(f"[warn] cannot resolve {handle!r}")
            continue
        upl = uploads_pl(yt, cid)
        if not upl:
            print(f"[warn] no uploads playlist for {cid}")
            continue

        for page in walk_pl_pages(yt, upl):
            ids = [it["snippet"]["resourceId"]["videoId"] for it in page]
            durations = fetch_durations(yt, ids)

            for it in page:
                vid = it["snippet"]["resourceId"]["videoId"]
                pub = isoparse(it["snippet"]["publishedAt"])
                if pub < CUTOFF:
                    continue

                title = it["snippet"]["title"]
                if "#shorts" in title.lower() or durations.get(vid, 0) <= SHORTS_MAXS:
                    continue  # skip shorts for POV channels

                if using_fallback:
                    raw_tok = extract_fallback_player(title)
                    nick = raw_tok.lower() if raw_tok else None
                    team = None
                else:
                    tokens = TOKEN.findall(title)
                    match  = next((t for t in tokens
                                   if t.lower() in whitelist_lc and t.lower() not in BLACKLIST),
                                  None)
                    nick = canonical.get(match.lower()) if match else None
                    team = nick_to_team.get(nick) if nick else None

                if nick:
                    counter[nick] += 1

                vids.append({
                    "id":        vid,
                    "title":     title,
                    "channel":   label,
                    "player":    nick,
                    "team":      team,
                    "map":       detect_map(title),
                    "published": pub.isoformat()[:10],
                })

    # ── NadesOutHere — split into strategy (long) / utility (shorts) ──────
    noh_cid = chan_id(yt, NADESOUTHERE)
    if not noh_cid:
        print(f"[warn] cannot resolve {NADESOUTHERE!r}")
    else:
        noh_upl = uploads_pl(yt, noh_cid)
        if not noh_upl:
            print(f"[warn] no uploads playlist for NadesOutHere")
        else:
            for page in walk_pl_pages(yt, noh_upl):
                ids = [it["snippet"]["resourceId"]["videoId"] for it in page]
                durations = fetch_durations(yt, ids)

                for it in page:
                    vid = it["snippet"]["resourceId"]["videoId"]
                    pub = isoparse(it["snippet"]["publishedAt"])
                    if pub < CUTOFF:
                        continue

                    title    = it["snippet"]["title"]
                    is_short = "#shorts" in title.lower() or durations.get(vid, 0) <= SHORTS_MAXS
                    category = "utility" if is_short else "strategy"
                    game_map = detect_map(title)

                    # Only include if we can categorise by map
                    if not game_map:
                        continue

                    vids.append({
                        "id":        vid,
                        "title":     title,
                        "channel":   category,
                        "player":    None,
                        "team":      None,
                        "map":       game_map,
                        "published": pub.isoformat()[:10],
                    })

    # ── Threshold filter for POV players ──────────────────────────────────
    keep = {p for p, n in counter.items() if n >= MIN_VIDEOS}
    for v in vids:
        if v.get("player") and v["player"] not in keep:
            v["player"] = None

    vids.sort(key=lambda v: v["published"], reverse=True)

    out_dir = Path("docs/data")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "videos.json").write_text(json.dumps(vids, indent=2))

    strategy_count = sum(1 for v in vids if v["channel"] == "strategy")
    utility_count  = sum(1 for v in vids if v["channel"] == "utility")
    print(f"[info] wrote {len(vids)} videos "
          f"({len(keep)} players, {strategy_count} strategy, {utility_count} utility)")

if __name__ == "__main__":
    main()
