from googleapiclient.discovery import build
from dateutil.parser import isoparse
from pathlib import Path
import json, os, re, datetime as dt
from hltv_async_api import Hltv 

YT_KEY    = os.getenv("YT_API_KEY")
CHANNELS  = {
    "lim":             "UC6eBEfV8x_Jc1IZ2Ftn8LwQ",
    "pov_highlights":  "UClkK9N8HreKW0vZQmlQ5Kvg",
    "nebula":          "UCQ3nz4Z_r5fR2aAlmLlgNOA",
}
MAPS = {"mirage","inferno","nuke","ancient","anubis","vertigo","overpass","dust2"}

def get_upload_playlist_id(y, channel_id):
    cd = y.channels().list(id=channel_id, part="contentDetails").execute()
    return cd["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

def scan_channel(y, upload_pl):
    vids, nextp = [], None
    while True:
        res = y.playlistItems().list(
            playlistId=upload_pl, part="snippet", maxResults=50,
            pageToken=nextp
        ).execute()
        vids.extend(res["items"])
        nextp = res.get("nextPageToken")
        if not nextp: break
    return vids

def parse_title(t):
    t_low = t.lower()
    map_hit = next((m for m in MAPS if m in t_low), None)
    player = re.split(r"[-|]|vs", t)[0].strip()
    return player, map_hit

hltv = Hltv()                                # reuse one instance per run

def enrich_player(player_name: str) -> str | None:
    """Return the player’s current team (or None) using HLTV."""
    try:
        match = hltv.search_players(player_name, size=1)
        return match[0]["team"]["name"] if match else None
    except Exception:
        return None

def main():
    y = build("youtube", "v3", developerKey=YT_KEY)
    existing = json.loads(Path("data/videos.json").read_text()) if Path("data/videos.json").exists() else []
    ids_seen = {v["id"] for v in existing}

    for chan_name, chan_id in CHANNELS.items():
        upl = get_upload_playlist_id(y, chan_id)
        for item in scan_channel(y, upl):
            vid = item["snippet"]["resourceId"]["videoId"]
            if vid in ids_seen: continue
            title = item["snippet"]["title"]
            player, gmap = parse_title(title)
            team  = enrich_player(player)
            entry = {
                "id": vid,
                "title": title,
                "channel": chan_name,
                "player": player,
                "team": team,
                "map": gmap,
                "published": item["snippet"]["publishedAt"][:10]
            }
            existing.append(entry)
            ids_seen.add(vid)

    existing.sort(key=lambda v: isoparse(v["published"]), reverse=True)
    Path("data").mkdir(exist_ok=True)
    Path("data/videos.json").write_text(json.dumps(existing, indent=2))

if __name__ == "__main__":
    main()
