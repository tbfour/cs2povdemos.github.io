async function load() {
  // ── 1. Fetch catalogue ──────────────────────────────────────────────────
  const res  = await fetch("data/videos.json");   // JSON lives inside /docs/data
  const data = await res.json();

  // ── 2. Build unique sets for filters ────────────────────────────────────
  const teamSet   = new Set(data.map(v => v.team).filter(Boolean));
  const playerSet = new Set(data.map(v => v.player));
  const mapSet    = new Set(data.map(v => v.map).filter(Boolean));

  // helper to populate a <select> and return the element
  const sel = (id, set) => {
    const el = document.getElementById(id);
    [...set].sort().forEach(v => el.insertAdjacentHTML("beforeend", `<option>${v}</option>`));
    el.addEventListener("change", render);
    return el;
  };

  const teamSel   = sel("team",   teamSet);
  const playerSel = sel("player", playerSet);
  const mapSel    = sel("map",    mapSet);

  // ── 3. Render cards based on current filter state ───────────────────────
  function render() {
    const t = teamSel.value,
          p = playerSel.value,
          m = mapSel.value;

    const wrap = document.getElementById("videos");
    wrap.innerHTML = "";

    data
      .filter(v =>
        (!t || v.team   === t) &&
        (!p || v.player === p) &&
        (!m || v.map    === m)
      )
      .forEach(v => {
        wrap.insertAdjacentHTML(
          "beforeend",
          `<div class="card">
             <iframe src="https://www.youtube.com/embed/${v.id}" allowfullscreen></iframe>
             <div class="card-info">
               <strong>${v.player}</strong> – ${v.map ?? "unknown"} (${v.team ?? "free-agent"})
             </div>
           </div>`
        );
      });
  }
  render();                       // initial draw

  // ── 4. Dark / light theme toggle ────────────────────────────────────────
  const btn  = document.getElementById("toggleTheme");
  const icon = document.getElementById("iconTheme");

  function setTheme(mode) {
    document.body.className = mode;
    icon.innerHTML = mode === "theme-dark"
      // moon icon
      ? '<path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>'
      // sun icon
      : '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.36 6.36l-1.42-1.42M6.05 6.05L4.64 4.64m0 13.72l1.41-1.41m12.73-12.73l-1.41 1.41M12 7a5 5 0 000 10a5 5 0 000-10z"/>';
  }

  btn.addEventListener("click", () => {
    const next = document.body.className.includes("dark") ? "theme-light" : "theme-dark";
    setTheme(next);
  });

  // initialise to whatever class is already on <body>
  setTheme(document.body.className);
}

load();
