// docs/app.js
(async function () {
  // --------------------------- Load catalogue ---------------------------
  const res = await fetch("data/videos.json", { cache: "no-store" });
  const data = await res.json();

  // Normalize fields to avoid literal "null"/"undefined"
  const norm = (v) => (v === null || v === undefined ? "" : String(v));
  data.forEach(v => {
    v.player    = norm(v.player);     // kept for info row; not used for player filter now
    v.team      = norm(v.team);
    v.map       = norm(v.map);
    v.title     = norm(v.title);
    v.id        = norm(v.id);
    v.channel   = norm(v.channel);
    v.published = norm(v.published);
  });

  // ---------------------- First-word player extraction -------------------
  // Stopwords to avoid obvious non-player "first words"
  const STOP = new Set([
    "cs2","csgo","faceit","pov","demo","highlights","highlight",
    "vs","clutch","the","a","an","of","on","for","and","or","with",
    // common map names
    "mirage","inferno","nuke","ancient","anubis","vertigo","overpass","dust2"
  ]);

  const firstToken = (title) => {
    // first alnum/underscore/hyphen token
    const m = title.match(/[A-Za-z0-9_-]+/);
    return m ? m[0] : "";
  };

  // Precompute first word (lower) for each video
  data.forEach(v => {
    const tok = firstToken(v.title);
    v._firstLower = tok.toLowerCase();
    v._firstDisplay = tok; // original casing as appears in the title
  });

  // Count occurrences of first words, ignoring stopwords and empties
  const counts = new Map();             // lower -> count
  const displayFor = new Map();         // lower -> first seen display form
  for (const v of data) {
    const lower = v._firstLower;
    if (!lower || STOP.has(lower)) continue;
    counts.set(lower, (counts.get(lower) || 0) + 1);
    if (!displayFor.has(lower)) displayFor.set(lower, v._firstDisplay);
  }

  // Only include names that appear > 7 times (i.e., >= 8)
  const PLAYER_MIN = 8;
  const playerLowerList = [...counts.entries()]
    .filter(([lower, n]) => n >= PLAYER_MIN)
    .map(([lower]) => lower);

  // Build display list and a lookup map display -> lower
  const displayToLower = new Map();
  const playerDisplayList = playerLowerList
    .map(lower => {
      const disp = displayFor.get(lower) || lower;
      displayToLower.set(disp, lower);
      return disp;
    })
    .sort((a,b) => a.localeCompare(b));

  // --------------------------- Option sets ------------------------------
  const isReal = (v) => v && v !== "null" && v !== "undefined";
  const teamSet   = new Set(data.map(v => v.team).filter(isReal));
  const mapSet    = new Set(data.map(v => v.map).filter(isReal));

  // --------------------------- DOM helpers ------------------------------
  const $ = (sel, root = document) => root.querySelector(sel);

  const ensureFiltersContainer = () => {
    let wrap = $(".filters");
    if (!wrap) {
      const header = $("header") || document.body;
      wrap = document.createElement("div");
      wrap.className = "filters";
      header.prepend(wrap);
    }
    return wrap;
  };

  const makeFilter = (key, label, values) => {
    const wrap = ensureFiltersContainer();
    const block = document.createElement("div");
    block.className = "filter";

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = `Search ${label}`;
    input.setAttribute("list", `${key}List`);
    input.id = `${key}Input`;
    input.autocomplete = "off";

    const list = document.createElement("datalist");
    list.id = `${key}List`;

    values.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v;
      list.appendChild(opt);
    });

    block.appendChild(input);
    block.appendChild(list);
    wrap.appendChild(block);
    return input;
  };

  // Create the three searchable dropdowns
  const teamInput   = makeFilter("team",   "Team",   [...teamSet].sort());
  const playerInput = makeFilter("player", "Player", playerDisplayList); // <-- new method
  const mapInput    = makeFilter("map",    "Map",    [...mapSet].sort());

  // ESC clears; Enter applies
  [teamInput, playerInput, mapInput].forEach(inp => {
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { inp.value = ""; render(0); }
      if (e.key === "Enter")  { render(0); }
    });
    inp.addEventListener("change", () => render(0));
  });

  // --------------------------- Pagination --------------------------------
  const PAGE_SIZE = 15;
  let page = 0;

  const pager = document.createElement("div");
  pager.className = "pager";
  pager.innerHTML = `
    <button id="prevPage" disabled>‹ Prev</button>
    <span id="pageInfo"></span>
    <button id="nextPage">Next ›</button>`;
  document.body.appendChild(pager);
  const prevBtn  = $("#prevPage", pager);
  const nextBtn  = $("#nextPage", pager);
  const pageInfo = $("#pageInfo", pager);

  prevBtn.onclick = () => { if (page>0) { page--; render(); } };
  nextBtn.onclick = () => { page++; render(); };

  // ----------------------------- Theme -----------------------------------
  const themeBtn  = $("#toggleTheme");
  const themeIcon = $("#iconTheme");

  const setTheme = (mode) => {
    document.body.className = mode;
    localStorage.setItem("theme", mode);
    if (themeIcon) {
      themeIcon.innerHTML = mode.includes("dark")
        ? '<path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>'
        : '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.36 6.36l-1.42-1.42M6.05 6.05L4.64 4.64m0 13.72l1.41-1.41m12.73-12.73l-1.41 1.41M12 7a5 5 0 000 10a5 5 0 000-10z"/>';
    }
  };

  const savedTheme = localStorage.getItem("theme");
  setTheme(savedTheme || document.body.className || "theme-dark");
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const next = document.body.className.includes("dark") ? "theme-light" : "theme-dark";
      setTheme(next);
    });
  }

  // --------------------------- Mount the grid ----------------------------
  let grid = document.getElementById("videos");
  const filtersWrap = ensureFiltersContainer();
  if (!grid) {
    grid = document.createElement("div");
    grid.id = "videos";
    filtersWrap.insertAdjacentElement("afterend", grid);
  }
  grid.classList.add("grid");

  // --------------------------- Rendering ---------------------------------
  // exact match to a provided option; otherwise treat as "no filter"
  const exactOrEmpty = (val, optionsArray) => {
    const x = (val || "").trim();
    if (!x) return "";
    const hit = optionsArray.find(v => v.toLowerCase() === x.toLowerCase());
    return hit || "";
  };

  function applyFilters() {
    // Team / Map filter from data fields
    const t = exactOrEmpty(teamInput.value,   [...teamSet]);
    const m = exactOrEmpty(mapInput.value,    [...mapSet]);

    // Player filter based on first-word method
    const pDisplay = exactOrEmpty(playerInput.value, playerDisplayList);
    const pLower = pDisplay ? (displayToLower.get(pDisplay) || pDisplay.toLowerCase()) : "";

    return data.filter(v =>
      (!t || v.team === t) &&
      (!m || v.map  === m) &&
      (!pLower || v._firstLower === pLower)
    );
  }

  function render(goToPage = page) {
    const filtered = applyFilters();

    const maxPage = Math.max(0, Math.ceil(filtered.length / PAGE_SIZE) - 1);
    page = Math.min(Math.max(0, goToPage), maxPage);

    const slice = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

    grid.innerHTML = "";
    if (!slice.length) {
      grid.insertAdjacentHTML("beforeend",
        `<div class="empty">No videos match your filters.</div>`);
    } else {
      slice.forEach(v => {
        const info = [
          v._firstDisplay ? `<strong>${escapeHtml(v._firstDisplay)}</strong>` : "",
          v.map ? `${escapeHtml(v.map)}` : "",
          v.team ? `${escapeHtml(v.team)}` : ""
        ].filter(Boolean).join(" — ");

        grid.insertAdjacentHTML("beforeend", `
          <div class="card">
            <iframe src="https://www.youtube.com/embed/${encodeURIComponent(v.id)}"
                    allowfullscreen loading="lazy"
                    referrerpolicy="strict-origin-when-cross-origin"></iframe>
            <div class="card-title">${escapeHtml(v.title)}</div>
            ${info ? `<div class="card-info">${info}</div>` : ""}
          </div>
        `);
      });
    }

    pageInfo.textContent = `${filtered.length ? page + 1 : 0} / ${maxPage + 1}`;
    prevBtn.disabled = page === 0;
    nextBtn.disabled = page === maxPage || filtered.length === 0;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));
  }

  // Initial render
  render(0);
})();
