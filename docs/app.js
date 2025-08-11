// docs/app.js
(async function () {
  // --------------------------- Load catalogue ---------------------------
  const res = await fetch("data/videos.json", { cache: "no-store" });
  const data = await res.json();

  // Normalize to avoid literal "null"/"undefined"
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

  // ---------------------- First-word player extraction -------------------
  // First token = first [A-Za-z0-9_-]+  (skips emojis like 🔥 and punctuation)
  const firstToken = (title) => {
    const m = title.match(/[A-Za-z0-9_-]+/);
    return m ? m[0] : "";
  };

  data.forEach(v => {
    const tok = firstToken(v.title);
    v._firstLower   = tok.toLowerCase();
    v._firstDisplay = tok; // keep original casing as seen in title
  });

  // Count occurrences of first words (ignore empty)
  const counts = new Map();     // lower -> count
  const displayFor = new Map(); // lower -> display
  for (const v of data) {
    const lower = v._firstLower;
    if (!lower) continue;
    counts.set(lower, (counts.get(lower) || 0) + 1);
    if (!displayFor.has(lower)) displayFor.set(lower, v._firstDisplay);
  }

  // Only expose players that appear ≥8 times
  const PLAYER_MIN = 8;
  const strongPlayersLower = [...counts.entries()]
    .filter(([_, n]) => n >= PLAYER_MIN)
    .map(([lower]) => lower);

  // Build display list and lookup
  const displayToLower = new Map();
  const playerDisplayList = strongPlayersLower
    .map(lower => {
      const disp = displayFor.get(lower) || lower;
      displayToLower.set(disp, lower);
      return disp;
    })
    .sort((a,b) => a.localeCompare(b));

  // --------------------------- Other option sets -------------------------
  const isReal = (v) => v && v !== "null" && v !== "undefined";
  const teamSet = new Set(data.map(v => v.team).filter(isReal));
  const mapSet  = new Set(data.map(v => v.map).filter(isReal));

  // --------------------------- DOM helpers -------------------------------
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

  // Build inputs
  const teamInput   = makeFilter("team",   "Team",   [...teamSet].sort());
  const playerInput = makeFilter("player", "Player", playerDisplayList);
  const mapInput    = makeFilter("map",    "Map",    [...mapSet].sort());

  // Prevent Enter from reloading page if inside a <form>
  [teamInput, playerInput, mapInput].forEach(inp => {
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); render(0); }
      if (e.key === "Escape") { e.preventDefault(); inp.value = ""; render(0); }
    });
    // Live filtering as you type
    inp.addEventListener("input",  () => render(0));
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
  // Exact match to an option; otherwise substring match on first word
  const pickExactOrSub = (val, optionsArray) => {
    const q = (val || "").trim();
    if (!q) return { mode: "none", value: "" };
    const exact = optionsArray.find(v => v.toLowerCase() === q.toLowerCase());
    return exact ? { mode: "exact", value: exact } : { mode: "sub", value: q.toLowerCase() };
  };

  function applyFilters() {
    // Team / Map use exact match against sets
    const t = (teamInput.value || "").trim();
    const m = (mapInput.value  || "").trim();
    const teamExact = [...teamSet].find(v => v.toLowerCase() === t.toLowerCase()) || "";
    const mapExact  = [...mapSet].find(v => v.toLowerCase()  === m.toLowerCase()) || "";

    // Player: first-word logic
    const playerPick = pickExactOrSub(playerInput.value, playerDisplayList);
    let passesPlayer;
    if (playerPick.mode === "none") {
      passesPlayer = () => true;
    } else if (playerPick.mode === "exact") {
      const lower = (displayToLower.get(playerPick.value) || playerPick.value.toLowerCase());
      passesPlayer = (v) => v._firstLower === lower;
    } else {
      const ql = playerPick.value; // lowercase substring
      passesPlayer = (v) => v._firstLower.includes(ql);
    }

    return data.filter(v =>
      (!teamExact || v.team === teamExact) &&
      (!mapExact  || v.map  === mapExact)  &&
      passesPlayer(v)
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

  // Minimal CSS safety net (in case theme misses our classes)
  (function injectFallbackCSS(){
    const style = document.createElement("style");
    style.textContent = `
      #videos.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:18px;padding:16px 12px 32px}
      .card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);border-radius:14px;overflow:hidden;box-shadow:0 6px 20px rgba(0,0,0,.25)}
      .card iframe{width:100%;aspect-ratio:16/9;border:0;background:#000;display:block}
      .card-title{padding:10px 12px 6px;font-weight:600}
      .card-info{padding:0 12px 12px;opacity:.85}
      .filters{display:grid;grid-auto-flow:column;gap:10px;padding:12px;align-items:center}
      .filters .filter input{width:100%;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:8px 10px;color:inherit;outline:none}
      .pager{display:flex;gap:10px;align-items:center;justify-content:center;padding:8px 0 40px}
      .pager button{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);color:inherit;border-radius:8px;padding:6px 10px;cursor:pointer}
      .empty{padding:32px;opacity:.8;text-align:center}
    `;
    document.head.appendChild(style);
  })();

  // Initial render
  render(0);
})();
