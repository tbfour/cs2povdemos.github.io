"""
Fetch player and map thumbnails from Liquipedia into docs/img/, and write
docs/data/images.json for the site to consume.

Liquipedia content is CC-BY-SA 3.0, so the site must credit it — see the
attribution note rendered in the footer (docs/index.html).

Their API terms (https://liquipedia.net/api-terms-of-use) require a
descriptive User-Agent, gzip, and rate limiting. This script batches title
lookups (50 per call, the API maximum) and sleeps between every request, so
a full run is only a handful of API calls plus one download per new image.

Players come from whoever actually appears in docs/data/videos.json; maps are
the fixed pool the site displays. Anything without a usable image is simply
omitted from the manifest, and the site falls back to a silhouette (players)
or the existing gradient (maps).

Usage:
    python src/fetch_images.py           # skip images already downloaded
    python src/fetch_images.py --force   # re-download everything
"""

from pathlib import Path
import json, re, sys, time
import requests

# ── Config ───────────────────────────────────────────────────────────────
API   = "https://liquipedia.net/counterstrike/api.php"
ROOT  = Path(__file__).resolve().parent.parent
DOCS  = ROOT / "docs"

# Liquipedia asks for a descriptive agent so they can get in touch. The repo
# URL is the contact point; put a real address here if you'd rather they mail
# you directly.
USER_AGENT = "cs2povdemos-image-fetcher/1.0 (https://github.com/tbfour/cs2povdemos.github.io)"

API_DELAY      = 2.0   # seconds between api.php calls, per their terms
DOWNLOAD_DELAY = 1.0   # seconds between image downloads
BATCH          = 50    # max titles per API query
THUMB_WIDTH    = 400

POV_CHANNELS = {"lim", "pov_highlights", "nebula"}

# Must stay in sync with ALL_MAPS in docs/app.js.
MAPS = ["mirage", "dust2", "ancient", "inferno", "nuke", "overpass", "anubis"]

# Map slug -> Liquipedia title. Bare map titles redirect to the /cs2 page, and
# `redirects=1` follows that for us, but being explicit avoids surprises if a
# redirect is ever repointed at a CS:GO-era page. Note Liquipedia spells it
# "Dust II", not "Dust2".
MAP_TITLES = {m: f"{'Dust II' if m == 'dust2' else m.capitalize()}/cs2" for m in MAPS}

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})


def api(**params):
    """One rate-limited api.php GET."""
    params.setdefault("format", "json")
    params.setdefault("formatversion", 2)
    params.setdefault("action", "query")
    r = session.get(API, params=params, timeout=30)
    r.raise_for_status()
    time.sleep(API_DELAY)
    return r.json()


def chunked(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def infobox_images(titles, require):
    """{requested title -> image filename} for pages whose infobox matches
    `require` (a regex) and carries an image."""
    found = {}
    for batch in chunked(titles, BATCH):
        data = api(
            prop="revisions", rvprop="content", rvslots="main",
            titles="|".join(batch), redirects=1,
        )
        query = data.get("query", {})

        # redirects=1 rewrites titles, so map the result back to what we asked
        resolved = {r["to"]: r["from"] for r in query.get("redirects", [])}
        normal   = {n["to"]: n["from"] for n in query.get("normalized", [])}

        for page in query.get("pages", []):
            if page.get("missing"):
                continue
            revs = page.get("revisions")
            if not revs:
                continue
            text = revs[0]["slots"]["main"]["content"]

            # Guard against a nickname colliding with a team or disambiguation
            # page — "Niko" is a different article from the CS star's "NiKo".
            if not re.search(require, text, re.I):
                continue

            m = re.search(r"^\s*\|\s*image\s*=\s*(.+?)\s*$", text, re.M)
            if not m or not m.group(1):
                continue

            title = page["title"]
            title = resolved.get(title, title)
            title = normal.get(title, title)
            found[title] = m.group(1)
    return found


def search_titles(name, limit=3):
    """Candidate page titles for `name`, best first.

    MediaWiki only auto-capitalises a title's first letter, so lowercase
    nicknames miss pages like ZywOo, M0NESY and YEKINDAR on a direct lookup.
    Search is case-insensitive and ranks the canonical page first.

    More than one candidate is returned because the top hit is sometimes a
    disambiguation page — "ScreaM" is a dab, the player is at
    "ScreaM (Belgian player)" — and those get filtered out by the infobox
    guard, letting the next candidate through.
    """
    data = api(list="search", srsearch=name, srlimit=limit)
    return [h["title"] for h in data.get("query", {}).get("search", [])]


def thumb_urls(filenames):
    """{filename -> thumbnail URL} at THUMB_WIDTH."""
    urls = {}
    for batch in chunked(filenames, BATCH):
        data = api(
            prop="imageinfo", iiprop="url", iiurlwidth=THUMB_WIDTH,
            titles="|".join(f"File:{f}" for f in batch),
        )
        query = data.get("query", {})
        normal = {n["to"]: n["from"] for n in query.get("normalized", [])}

        for page in query.get("pages", []):
            info = page.get("imageinfo")
            if not info:
                continue
            title = normal.get(page["title"], page["title"])
            urls[title.removeprefix("File:")] = info[0].get("thumburl") or info[0]["url"]
    return urls


def download(url, dest, force):
    if dest.exists() and not force:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = session.get(url, timeout=60)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! download failed: {e}")
        return False
    dest.write_bytes(r.content)
    time.sleep(DOWNLOAD_DELAY)
    return True


def collect(kind, slug_to_title, force, require, use_search=False, existing=None):
    """Resolve titles -> images -> local files. Returns {slug: relative path}."""
    print(f"\n== {kind} ({len(slug_to_title)}) ==")

    # Carry forward anything already on disk and skip its lookups entirely, so
    # a scheduled run only talks to Liquipedia about players new to the
    # catalogue instead of re-querying all of them every day.
    existing = existing or {}
    manifest, pending = {}, {}
    for slug, title in slug_to_title.items():
        rel = existing.get(slug)
        if not force and rel and (DOCS / rel).exists():
            manifest[slug] = rel
        else:
            pending[slug] = title

    print(f"  cached: {len(manifest)} | to fetch: {len(pending)}")
    if not pending:
        return manifest
    slug_to_title = pending

    by_title = infobox_images(list(slug_to_title.values()), require)
    print(f"  direct lookup: {len(by_title)}/{len(slug_to_title)}")

    # Second pass: search for the ones a direct title lookup could not resolve.
    if use_search:
        missed = [s for s, t in slug_to_title.items() if t not in by_title]
        candidates = {s: search_titles(s) for s in missed}

        pool = sorted({t for ts in candidates.values() for t in ts})
        extra = infobox_images(pool, require) if pool else {}

        resolved = []
        for slug, titles in candidates.items():
            # First candidate that survived the infobox guard wins.
            hit = next((t for t in titles if t in extra), None)
            if hit:
                slug_to_title[slug] = hit
                by_title[hit] = extra[hit]
                resolved.append(slug)
        print(f"  via search:    +{len(resolved)} ({', '.join(sorted(resolved)) or '-'})")

    urls = thumb_urls(sorted(set(by_title.values()))) if by_title else {}

    for slug, title in slug_to_title.items():
        filename = by_title.get(title)
        url = urls.get(filename) if filename else None
        if not url:
            print(f"  - {slug}: no image (will fall back)")
            continue

        ext  = Path(url).suffix.lower() or ".jpg"
        rel  = f"img/{kind}/{slug}{ext}"
        if download(url, DOCS / rel, force):
            manifest[slug] = rel
            print(f"  + {slug} -> {rel}")
    return manifest


def main():
    force = "--force" in sys.argv

    videos = json.loads((DOCS / "data" / "videos.json").read_text(encoding="utf-8"))
    players = sorted({
        v["player"] for v in videos
        if v.get("player") and v.get("channel") in POV_CHANNELS
    })

    # MediaWiki capitalises the first letter of a title automatically, so the
    # lowercase nicknames the catalogue stores resolve fine as-is.
    out = DOCS / "data" / "images.json"
    previous = {}
    if out.exists() and not force:
        try:
            previous = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("! existing images.json is unreadable; refetching everything")

    manifest = {
        "players": collect("players", {p: p for p in players}, force,
                           require=r"\{\{\s*Infobox player", use_search=True,
                           existing=previous.get("players")),
        "maps":    collect("maps", dict(MAP_TITLES), force,
                           require=r"\{\{\s*Infobox",
                           existing=previous.get("maps")),
    }

    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT)} "
          f"({len(manifest['players'])} players, {len(manifest['maps'])} maps)")


if __name__ == "__main__":
    main()
