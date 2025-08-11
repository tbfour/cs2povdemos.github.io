// docs/app.js
(async function () {
  // --------------------------- Load catalogue ---------------------------
  const res = await fetch("data/videos.json", { cache: "no-store" });
  const data = await res.json();

  // Normalize fields so we never render literal "null"/"undefined"
  const norm = (v) => (v === null || v === undefined ? "" : String(v));
  data.forEach(v => {
    v.player    = norm(v.player);
    v.team      = norm(v.team);
    v.map       = norm(v.map);
    v.title     = norm(v.title);
    v.id        = norm(v.id);
    v.channel   = norm(v.channel);
    v.published = norm(v.published);
  });

  // Build option sets (filter out empty/null/undefined)
  const isReal = (v) => v && v !== "null" && v !== "undefined";
  const teamSet   = new Set(data.map(v => v.team).filter(isReal));
  const playerSet = new Set(data.map(v => v.player).filter(isReal));
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

    [...values].sort((a,b)=> a.localeCompare(b)).forEach(v => {
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
  const teamInput   = makeFilter("team",   "Team",   teamSet);
  const playerInput = makeFilter("player", "Player", playerSet);
  const mapInput    = makeFilter("map",    "Map",    mapSet);

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
  const prevBtn = $("#prevPage", pager);
  const nextBtn = $("#nextPage", pager);
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

  // --------------------------- Rendering ---------------------------------
  const grid = document.createElement("main");
  grid.id = "videos";
  grid.className = "grid";
  if (!$("main.grid")) document.body.insertBefore(grid, pager);

  // Coerce input to an exact option; otherwise treat as "no filter"
  const exactOrEmpty = (val, setValues) => {
    const x = (val || "").trim();
    if (!x) return "";
    const hit = [...setValues].find(v => v.toLowerCase() === x.toLowerCase());
    return hit || "";
  };

  function applyFilters() {
    const t = exactOrEmpty(teamInput.value,   teamSet);
    const p = exactOrEmpty(playerInput.value, playerSet);
    const m = exactOrEmpty(mapInput.value,    mapSet);

    return data.filter(v =>
      (!t || v.team   === t) &&
      (!p || v.player === p) &&
      (!m || v.map    === m)
    );
  }

  function render(goToPage = page) {
    const filtered = applyFilters();

    // Pagination envelope
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
          v.player ? `<strong>${escapeHtml(v.player)}</strong>` : "",
          v.map ? `${escapeHtml(v.map)}` : "",
          v.team ? `${escapeHtml(v.team)}` : ""
        ].filter(Boolean).join(" — ");

        grid.insertAdjacentHTML("beforeend", `
          <div class="card">
            <iframe src="https://www.youtube.com/embed/${encodeURIComponent(v.id)}"
                    allowfullscreen loading="lazy"></iframe>
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

  // Simple title escape
  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));
  }

  // Initial render
  render(0);
})();
