# cs2povdemos.github.io
automatically uploading cs2 pro pov demos from events/pugs

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
