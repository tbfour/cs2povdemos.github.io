async function load() {
  // 1. Fetch catalogue ----------------------------------------------------
  const res  = await fetch("data/videos.json");
  const data = await res.json();

  // 2. Build filter sets --------------------------------------------------
  const teamSet   = new Set(data.map(v => v.team).filter(Boolean));
  const playerSet = new Set(data.map(v => v.player));
  const mapSet    = new Set(data.map(v => v.map).filter(Boolean));

  // helper: create search+select pair
  function makeFilter(id, labelText, values) {
    const block = document.createElement("div");
    block.className = "filter-block";

    const search = document.createElement("input");
    search.type  = "text";
    search.placeholder = `Search ${labelText}`;
    search.className   = "search";

    const select = document.createElement("select");
    select.id = id;
    select.innerHTML = `<option value="">${labelText} ↓</option>` +
      [...values].sort().map(v => `<option>${v}</option>`).join("");

    // live-filter options
    search.addEventListener("input", () => {
      const q = search.value.toLowerCase();
      [...select.options].forEach(opt => {
        opt.hidden = q && !opt.text.toLowerCase().includes(q);
      });
    });
    // reset search when user picks an option
    select.addEventListener("change", () => { search.value = ""; page = 0; render(); });

    block.append(search, select);
    document.querySelector(".filters").appendChild(block);
    return select;
  }

  const teamSel   = makeFilter("team",   "Team",   teamSet);
  const playerSel = makeFilter("player", "Player", playerSet);
  const mapSel    = makeFilter("map",    "Map",    mapSet);

  // 3. Pagination + render -----------------------------------------------
  let page = 0;
  const PAGE_SIZE = 15;

  const pager = document.createElement("div");
  pager.className = "pager";
  pager.innerHTML = `
    <button id="prevPage" disabled>‹ Prev</button>
    <span id="pageInfo"></span>
    <button id="nextPage">Next ›</button>`;
  document.body.appendChild(pager);

  const prevBtn  = pager.querySelector("#prevPage");
  const nextBtn  = pager.querySelector("#nextPage");
  const pageInfo = pager.querySelector("#pageInfo");

  prevBtn.onclick = () => { page--; render(); };
  nextBtn.onclick = () => { page++; render(); };

  function render() {
    const t = teamSel.value,
          p = playerSel.value,
          m = mapSel.value;

    const filtered = data.filter(v =>
      (!t || v.team   === t) &&
      (!p || v.player === p) &&
      (!m || v.map    === m)
    );

    const maxPage = Math.max(0, Math.ceil(filtered.length / PAGE_SIZE) - 1);
    page = Math.min(page, maxPage);

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

    pageInfo.textContent = `${page + 1} / ${maxPage + 1}`;
    prevBtn.disabled = page === 0;
    nextBtn.disabled = page === maxPage;
  }
  render();

  // 4. Theme toggle -------------------------------------------------------
  const btn  = document.getElementById("toggleTheme");
  const icon = document.getElementById("iconTheme");

  function setTheme(mode) {
    document.body.className = mode;
    icon.innerHTML = mode === "theme-dark"
      ? '<path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>'
      : '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.36 6.36l-1.42-1.42M6.05 6.05L4.64 4.64m0 13.72l1.41-1.41m12.73-12.73l-1.41 1.41M12 7a5 5 0 000 10a5 5 0 000-10z"/>';
  }
  btn.onclick = () => {
    const next = document.body.className.includes("dark") ? "theme-light" : "theme-dark";
    setTheme(next);
  };
  setTheme(document.body.className);
}

load();
