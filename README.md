# cs2povdemos.github.io
automatically uploading cs2 pro pov demos from events/pugs

## Images

Player and map thumbnails come from [Liquipedia](https://liquipedia.net/counterstrike/)
(CC-BY-SA 3.0 — credited in the site footer, which the licence requires).

`src/fetch_images.py` downloads them into `docs/img/` and writes
`docs/data/images.json`, a manifest of `slug -> path`:

```json
{ "players": { "donk": "img/players/donk.jpg" },
  "maps":    { "mirage": "img/maps/mirage.jpg" } }
```

Anything absent from the manifest — or a path that 404s — falls back per card
to a silhouette (players) or the map gradient. Two players currently have no
Liquipedia page and render silhouettes by design.

```sh
python src/fetch_images.py           # skip images already on disk
python src/fetch_images.py --force   # re-download everything
```

The daily workflow runs this after the video scraper, so players new to the
catalogue pick up photos automatically. It is `continue-on-error`, so a
Liquipedia outage cannot block the `videos.json` refresh.

Note the fetcher resolves titles by search as well as direct lookup:
MediaWiki only auto-capitalises a title's *first* letter, so `zywoo` alone
misses `ZywOo`, and `niko` resolves to a different article than the CS
player's `NiKo`.

## Styling / build step

The header, tab bar and card grids are styled with Tailwind CSS v4.
`docs/tailwind.css` is a **compiled artifact** and is committed because GitHub
Pages serves the repo as-is with no build step.

After editing `docs/src/input.css`, regenerate it:

```sh
# one-time: grab the standalone CLI (no Node required)
curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64
chmod +x tailwindcss-linux-x64

./tailwindcss-linux-x64 -i docs/src/input.css -o docs/tailwind.css --minify
```

Everything else still lives in the hand-written `docs/theme.css`.
