// docs/app.js
(async function () {
  // ── Load data ────────────────────────────────────────────────────────
  const videos = await fetch("data/videos.json", { cache: "no-store" }).then(r => r.json());

  const norm = v => (v == null ? "" : String(v));
  videos.forEach(v => {
    v.player    = norm(v.player);
    v.team      = norm(v.team);
    v.map       = norm(v.map);
    v.title     = norm(v.title);
    v.id        = norm(v.id);
    v.channel   = norm(v.channel);
    v.published = norm(v.published);
  });

  const isReal = s => s && s !== "null" && s !== "undefined";

  // ── Build indexes ────────────────────────────────────────────────────
  const byPlayer      = new Map();  // player  → video[]  (POV channels)
  const playerTeam    = new Map();  // player  → team name
  const byMapPOV      = new Map();  // map key → video[]  (POV channels)
  const byMapStrategy = new Map();  // map key → video[]  (channel === "strategy")
  const byMapUtility  = new Map();  // map key → video[]  (channel === "utility")

  const POV_CHANNELS = new Set(["lim", "pov_highlights", "nebula"]);

  for (const v of videos) {
    const isPOV      = POV_CHANNELS.has(v.channel);
    const isStrategy = v.channel === "strategy";
    const isUtility  = v.channel === "utility";
    const mapKey     = v.map.toLowerCase().replace(/\s+/g, "");

    if (isPOV) {
      if (isReal(v.player)) {
        if (!byPlayer.has(v.player)) byPlayer.set(v.player, []);
        byPlayer.get(v.player).push(v);
        if (isReal(v.team) && !playerTeam.has(v.player)) playerTeam.set(v.player, v.team);
      }
      if (isReal(v.map)) {
        if (!byMapPOV.has(mapKey)) byMapPOV.set(mapKey, []);
        byMapPOV.get(mapKey).push(v);
      }
    } else if (isStrategy && isReal(v.map)) {
      if (!byMapStrategy.has(mapKey)) byMapStrategy.set(mapKey, []);
      byMapStrategy.get(mapKey).push(v);
    } else if (isUtility && isReal(v.map)) {
      if (!byMapUtility.has(mapKey)) byMapUtility.set(mapKey, []);
      byMapUtility.get(mapKey).push(v);
    }
  }

  // ── Map config (always show all 7 regardless of count) ───────────────
  const ALL_MAPS = [
    { key: "mirage",   label: "Mirage",   bg: "linear-gradient(145deg,#d4a450,#7a4510)" },
    { key: "dust2",    label: "Dust 2",   bg: "linear-gradient(145deg,#dcc060,#8a6010)" },
    { key: "ancient",  label: "Ancient",  bg: "linear-gradient(145deg,#3d8a50,#103820)" },
    { key: "inferno",  label: "Inferno",  bg: "linear-gradient(145deg,#e04820,#700800)" },
    { key: "nuke",     label: "Nuke",     bg: "linear-gradient(145deg,#4080c0,#103060)" },
    { key: "overpass", label: "Overpass", bg: "linear-gradient(145deg,#7060b8,#280878)" },
    { key: "anubis",   label: "Anubis",   bg: "linear-gradient(145deg,#c8a820,#504000)" },
  ];

  // ── State ─────────────────────────────────────────────────────────────
  const PAGE  = 15;
  const state = { tab: "players", player: null, map: null, page: 0 };

  // ── DOM ───────────────────────────────────────────────────────────────
  const app  = document.getElementById("app");
  const tabs = document.querySelectorAll(".tab[data-tab]");

  tabs.forEach(btn => btn.addEventListener("click", () => {
    if (btn.dataset.tab === state.tab) return;
    state.tab    = btn.dataset.tab;
    state.player = null;
    state.map    = null;
    state.page   = 0;
    tabs.forEach(t => t.classList.toggle("active", t === btn));
    render();
  }));

  // ── Theme ─────────────────────────────────────────────────────────────
  const themeBtn  = document.getElementById("toggleTheme");
  const themeIcon = document.getElementById("iconTheme");
  const setTheme  = mode => {
    document.body.className = mode;
    localStorage.setItem("theme", mode);
    if (themeIcon) themeIcon.innerHTML = mode.includes("dark")
      ? '<path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>'
      : '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.36 6.36l-1.42-1.42M6.05 6.05L4.64 4.64m0 13.72l1.41-1.41m12.73-12.73l-1.41 1.41M12 7a5 5 0 000 10a5 5 0 000-10z"/>';
  };
  setTheme(localStorage.getItem("theme") || "theme-dark");
  themeBtn?.addEventListener("click", () =>
    setTheme(document.body.className.includes("dark") ? "theme-light" : "theme-dark")
  );

  // ── Utilities ─────────────────────────────────────────────────────────
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g,
      c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }

  // ── Render dispatcher ─────────────────────────────────────────────────
  function render() {
    app.innerHTML = "";
    const { tab, player, map } = state;

    if (tab === "players") {
      if (player) {
        appendBackBar("Players", () => { state.player = null; render(); });
        appendSectionTitle(player);
        appendVideoGrid(byPlayer.get(player) || []);
      } else {
        appendPlayerGrid([...byPlayer.keys()].sort());
      }

    } else if (tab === "maps") {
      if (map) {
        const meta = ALL_MAPS.find(m => m.key === map);
        appendBackBar("Maps", () => { state.map = null; render(); });
        appendSectionTitle(meta?.label ?? map);
        appendVideoGrid(byMapPOV.get(map) || []);
      } else {
        appendMapGrid(byMapPOV, "Maps");
      }

    } else if (tab === "strategy") {
      if (map) {
        const meta = ALL_MAPS.find(m => m.key === map);
        appendBackBar("Strategy", () => { state.map = null; render(); });
        appendSectionTitle(meta?.label ?? map);
        appendVideoGrid(byMapStrategy.get(map) || []);
      } else {
        appendMapGrid(byMapStrategy, "Strategy");
      }

    } else { // utility
      if (map) {
        const meta = ALL_MAPS.find(m => m.key === map);
        appendBackBar("Utility", () => { state.map = null; render(); });
        appendSectionTitle(meta?.label ?? map);
        appendVideoGrid(byMapUtility.get(map) || []);
      } else {
        appendMapGrid(byMapUtility, "Utility");
      }
    }
  }

  // ── Back bar & section title ──────────────────────────────────────────
  function appendBackBar(label, onClick) {
    const bar = document.createElement("div");
    bar.className = "back-bar";
    bar.innerHTML = `<button class="back-btn">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="14" height="14">
        <path stroke-linecap="round" stroke-linejoin="round" d="M19 12H5M12 5l-7 7 7 7"/>
      </svg>${esc(label)}</button>`;
    bar.querySelector(".back-btn").addEventListener("click", onClick);
    app.appendChild(bar);
  }

  function appendSectionTitle(text) {
    const h = document.createElement("h2");
    h.className = "section-title";
    h.textContent = text;
    app.appendChild(h);
  }

  // ── Player grid ───────────────────────────────────────────────────────
  function appendPlayerGrid(players) {
    if (!players.length) {
      app.insertAdjacentHTML("beforeend",
        `<div class="empty">No player data yet — the scraper will populate this on next run.</div>`);
      return;
    }
    const grid = document.createElement("div");
    grid.className = "card-grid player-grid";
    for (const p of players) {
      const count = byPlayer.get(p)?.length ?? 0;
      const team  = playerTeam.get(p) ?? "";
      const card  = document.createElement("div");
      card.className = "player-card";
      card.innerHTML = `
        <div class="player-avatar">${esc(p.slice(0, 2).toUpperCase())}</div>
        <div class="player-name">${esc(p)}</div>
        ${team ? `<div class="player-team">${esc(team)}</div>` : ""}
        <div class="player-count">${count} video${count !== 1 ? "s" : ""}</div>`;
      card.addEventListener("click", () => { state.player = p; state.page = 0; render(); });
      grid.appendChild(card);
    }
    app.appendChild(grid);
  }

  // ── Map grid (shared by Maps, Strategy, Utility tabs) ─────────────────
  function appendMapGrid(mapIndex, tabLabel) {
    const grid = document.createElement("div");
    grid.className = "card-grid map-grid";
    for (const m of ALL_MAPS) {
      const count = mapIndex.get(m.key)?.length ?? 0;
      const card  = document.createElement("div");
      card.className = "map-card";
      card.style.background = m.bg;
      card.innerHTML = `
        <div class="map-card-inner">
          <div class="map-label">${esc(m.label)}</div>
          <div class="map-count">${count} video${count !== 1 ? "s" : ""}</div>
        </div>`;
      card.addEventListener("click", () => { state.map = m.key; state.page = 0; render(); });
      grid.appendChild(card);
    }
    app.appendChild(grid);
  }

  // ── Video grid ────────────────────────────────────────────────────────
  function appendVideoGrid(vids) {
    if (!vids.length) {
      app.insertAdjacentHTML("beforeend", `<div class="empty">No videos found.</div>`);
      return;
    }

    const maxPage = Math.max(0, Math.ceil(vids.length / PAGE) - 1);
    state.page = Math.min(Math.max(0, state.page), maxPage);
    const slice = vids.slice(state.page * PAGE, (state.page + 1) * PAGE);

    const grid = document.createElement("div");
    grid.className = "card-grid video-grid";
    for (const v of slice) {
      const info = [
        v.player ? `<strong>${esc(v.player)}</strong>` : "",
        v.map    ? esc(v.map)  : "",
        v.team   ? esc(v.team) : "",
      ].filter(Boolean).join(" — ");

      const card = document.createElement("div");
      card.className = "video-card";
      card.innerHTML = `
        <iframe src="https://www.youtube.com/embed/${encodeURIComponent(v.id)}"
                allowfullscreen loading="lazy"
                referrerpolicy="strict-origin-when-cross-origin"></iframe>
        <div class="card-title">${esc(v.title)}</div>
        ${info ? `<div class="card-info">${info}</div>` : ""}`;
      grid.appendChild(card);
    }
    app.appendChild(grid);

    if (maxPage > 0) {
      const pager = document.createElement("div");
      pager.className = "pager";
      pager.innerHTML = `
        <button class="pager-prev" ${state.page === 0 ? "disabled" : ""}>‹ Prev</button>
        <span class="pager-info">${state.page + 1} / ${maxPage + 1}</span>
        <button class="pager-next" ${state.page === maxPage ? "disabled" : ""}>Next ›</button>`;
      pager.querySelector(".pager-prev").addEventListener("click", () => { state.page--; render(); });
      pager.querySelector(".pager-next").addEventListener("click", () => { state.page++; render(); });
      app.appendChild(pager);
    }
  }

  render();
})();
