async function load() {
  // ── 1. Fetch catalogue ────────────────────────────────────────────────
  const res  = await fetch("data/videos.json");   // JSON lives inside /docs/data
  const data = await res.json();

  // ── 2. Build filter dropdowns ─────────────────────────────────────────
  const teamSet   = new Set(data.map(v => v.team).filter(Boolean));
  const playerSet = new Set(data.map(v => v.player));
  const mapSet    = new Set(data.map(v => v.map).filter(Boolean));

  const sel = (id, set) => {
    const el = document.getElementById(id);
    [...set].sort().forEach(v => el.insertAdjacentHTML("beforeend", `<option>${v}</option>`));
    el.addEventListener("change", () => { page = 0; render(); });
    return el;
  };
  const teamSel   = sel("team",   teamSet);
  const playerSel = sel("player", playerSet);
  const mapSel    = sel("map",    mapSet);

  // ── 3. Pagination + render ────────────────────────────────────────────
  let page = 0;
  const PAGE_SIZE = 15;

  // pager controls
  const pager = document.createElement("div");
  pager.className = "pager";
  pager.innerHTML = `
    <button id="prevPage" disabled>‹ Prev</button>
    <span id="pageInfo"></span>
    <button id="nextPage">Next ›</button>`;
  document.body.appendChild(pager);

  const prevBtn  = document.getElementById("prevPage");
  const nextBtn  = document.getElementById("nextPage");
  const pageInfo = document.getElementById("pageInfo");

  prevBtn.onclick = () => { page--; render(); };
  nextBtn.onclick = () => { page++; render(); };

  function render() {
    const t = teamSel.value,
          p = playerSel.value,
          m = mapSel.value;

    // filter first
    const filtered = data.filter(v =>
      (!t || v.team   === t) &&
      (!p || v.player === p) &&
      (!m || v.map    === m)
    );

    // adjust page if filter shrank list
    const maxPage = Math.max(0, Math.ceil(filtered.length / PAGE_SIZE) - 1);
    page = Math.min(page, maxPage);

    // slice for current page
    const slice = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

    const wrap = document.getElementById("videos");
    wrap.innerHTML = "";
    slice.forEach(v => {
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

    // update pager
    pageInfo.textContent = `${page + 1} / ${maxPage + 1}`;
    prevBtn.disabled = page === 0;
    nextBtn.disabled = page === maxPage;
  }
  render();   // initial draw

  // ── 4. Dark / light theme toggle ──────────────────────────────────────
  const btn  = document.getElementById("toggleTheme");
  const icon = document.getElementById("iconTheme");

  function setTheme(mode) {
    document.body.className = mode;
    icon.innerHTML = mode === "theme-dark"
      ? '<path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>'
      : '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.36 6.36l-1.42-1.42M6.05 6.05L4.64 4.64m0 13.72l1.41-1.41m12.73-12.73l-1.41 1.41M12 7a5 5 0 000 10a5 5 0 000-10z"/>';
  }

  btn.addEventListener("click", () => {
    const next = document.body.className.includes("dark") ? "theme-light" : "theme-dark";
    setTheme(next);
  });
  setTheme(document.body.className);   // initial
}

load();
