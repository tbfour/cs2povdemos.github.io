// docs/app.js
(async function () {
  // ── Load data ────────────────────────────────────────────────────────
  const videos = await fetch("data/videos.json", { cache: "no-store" }).then(r => r.json());

  // Optional image manifest — see docs/data/images.json.example. Absent or
  // malformed is fine: cards fall back to a silhouette / the map gradient.
  //   { "players": { "donk": "img/players/donk.jpg" },
  //     "maps":    { "mirage": "img/maps/mirage.jpg" } }
  const images = await fetch("data/images.json")
    .then(r => (r.ok ? r.json() : {}))
    .catch(() => ({}));
  const playerImg = name => images?.players?.[name] ?? null;
  const mapImg    = key  => images?.maps?.[key]     ?? null;

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

  // ── Bookmarks (persisted in localStorage) ────────────────────────────
  const BOOKMARK_KEY = "cs2pov_bookmarks";
  const bookmarks    = new Set(JSON.parse(localStorage.getItem(BOOKMARK_KEY) || "[]"));
  const saveBookmarks = () =>
    localStorage.setItem(BOOKMARK_KEY, JSON.stringify([...bookmarks]));

  // ── Build indexes ────────────────────────────────────────────────────
  const byPlayer      = new Map();
  const playerTeam    = new Map();
  const byMapPOV      = new Map();
  const byMapStrategy = new Map();
  const byMapUtility  = new Map();

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

  // ── Map config ────────────────────────────────────────────────────────
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
  const state = { tab: "players", player: null, map: null, q: "" };

  // ── DOM ───────────────────────────────────────────────────────────────
  const app  = document.getElementById("app");
  const tabs = document.querySelectorAll(".tab-btn[data-tab]");

  // ── Routing ───────────────────────────────────────────────────────────
  // Hash-based so deep links survive a refresh on GitHub Pages, which can't
  // rewrite unknown paths to index.html.
  //   #/players          #/players/donk
  //   #/maps             #/maps/mirage        #/maps/mirage?q=ace
  //   #/strategy         #/strategy/nuke
  //   #/utility          #/utility/mirage
  //   #/bookmarks
  const VALID_TABS = new Set(["players", "maps", "strategy", "utility", "bookmarks"]);
  const MAP_TABS   = new Set(["maps", "strategy", "utility"]);

  function parseHash() {
    const raw    = location.hash.replace(/^#\/?/, "");
    const cut    = raw.indexOf("?");
    const path   = cut === -1 ? raw : raw.slice(0, cut);
    const params = new URLSearchParams(cut === -1 ? "" : raw.slice(cut + 1));

    const [tabRaw, detailRaw] = path.split("/");
    const tab    = VALID_TABS.has(tabRaw) ? tabRaw : "players";
    const detail = detailRaw ? decodeURIComponent(detailRaw) : null;
    return {
      tab,
      player: tab === "players"  ? detail : null,
      map:    MAP_TABS.has(tab)  ? detail?.toLowerCase() ?? null : null,
      q:      params.get("q") ?? "",
    };
  }

  function hashFor(tab, detail, q) {
    const path = detail ? `#/${tab}/${encodeURIComponent(detail)}` : `#/${tab}`;
    return q ? `${path}?q=${encodeURIComponent(q)}` : path;
  }

  // Every navigation goes through the URL, so back/forward just work.
  // Omitting q clears any active search, which is what a tab/card click wants.
  function navigate(tab, detail, q) {
    const target = hashFor(tab, detail, q);
    if (location.hash === target) return;
    location.hash = target;
  }

  // Typing is not history-worthy: replaceState keeps the URL shareable without
  // pushing an entry per keystroke, and does not fire hashchange (no re-render,
  // so the input keeps focus and caret position).
  function syncSearchToUrl(q) {
    state.q = q.trim();
    const target = hashFor(state.tab, state.player ?? state.map, state.q);
    if (location.hash !== target) history.replaceState(null, "", target);
  }

  function applyHash() {
    Object.assign(state, parseHash());
    render();
  }

  tabs.forEach(btn => btn.addEventListener("click", () => navigate(btn.dataset.tab, null)));

  // ── Theme ─────────────────────────────────────────────────────────────
  const themeBtn  = document.getElementById("toggleTheme");
  const themeIcon = document.getElementById("iconTheme");
  const setTheme  = mode => {
    document.body.className = mode;
    document.documentElement.classList.toggle("dark", mode === "theme-dark");
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

  const SVG_NS = "http://www.w3.org/2000/svg";

  // Neutral head-and-shoulders placeholder for players with no photo.
  function makeSilhouette() {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "currentColor");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "silhouette");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d",
      "M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0 2c-4.42 0-8 2.24-8 5v1h16v-1c0-2.76-3.58-5-8-5Z");
    svg.appendChild(path);
    return svg;
  }

  // Lazy <img> that swaps itself out for `makeFallback()` if the file 404s,
  // so a partial manifest degrades per-card instead of showing broken images.
  function makeImageOrFallback(src, className, makeFallback) {
    if (!src) return makeFallback();
    const img = document.createElement("img");
    img.className = className;
    img.src       = src;
    img.alt       = "";
    img.loading   = "lazy";
    img.decoding  = "async";
    img.addEventListener("error", () => img.replaceWith(makeFallback()), { once: true });
    return img;
  }

  function makeBookmarkIcon(filled) {
    const ns   = "http://www.w3.org/2000/svg";
    const svg  = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width",  "15");
    svg.setAttribute("height", "15");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("fill", filled ? "currentColor" : "none");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", "M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z");
    svg.appendChild(p);
    return svg;
  }

  // ── Render dispatcher ─────────────────────────────────────────────────
  function render() {
    app.innerHTML = "";
    const { tab, player, map } = state;

    tabs.forEach(t => t.classList.toggle("active", t.dataset.tab === tab));

    if (tab === "players") {
      if (player) {
        appendBackBar("Players", () => navigate("players", null));
        appendSectionTitle(player);
        appendVideoGrid(byPlayer.get(player) || []);
      } else {
        appendPlayerGrid([...byPlayer.keys()].sort());
      }

    } else if (tab === "maps") {
      if (map) {
        const meta = ALL_MAPS.find(m => m.key === map);
        appendBackBar("Maps", () => navigate("maps", null));
        appendSectionTitle(meta?.label ?? map);
        appendVideoGrid(byMapPOV.get(map) || []);
      } else {
        appendMapGrid(byMapPOV);
      }

    } else if (tab === "strategy") {
      if (map) {
        const meta = ALL_MAPS.find(m => m.key === map);
        appendBackBar("Strategy", () => navigate("strategy", null));
        appendSectionTitle(meta?.label ?? map);
        appendVideoGrid(byMapStrategy.get(map) || []);
      } else {
        appendMapGrid(byMapStrategy);
      }

    } else if (tab === "utility") {
      if (map) {
        const meta = ALL_MAPS.find(m => m.key === map);
        appendBackBar("Utility", () => navigate("utility", null));
        appendSectionTitle(meta?.label ?? map);
        appendVideoGrid(byMapUtility.get(map) || []);
      } else {
        appendMapGrid(byMapUtility);
      }

    } else if (tab === "bookmarks") {
      const saved = videos.filter(v => bookmarks.has(v.id));
      appendSectionTitle(`Bookmarks${saved.length ? ` (${saved.length})` : ""}`);
      if (!saved.length) {
        app.insertAdjacentHTML("beforeend",
          `<div class="empty">No bookmarks yet — click the ribbon icon on any video to save it.</div>`);
      } else {
        appendVideoGrid(saved);
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
        <div class="player-avatar"></div>
        <div class="player-name">${esc(p)}</div>
        ${team ? `<div class="player-team">${esc(team)}</div>` : ""}
        <div class="player-count">${count} video${count !== 1 ? "s" : ""}</div>`;
      card.querySelector(".player-avatar")
          .appendChild(makeImageOrFallback(playerImg(p), "avatar-img", makeSilhouette));
      card.addEventListener("click", () => navigate("players", p));
      grid.appendChild(card);
    }
    app.appendChild(grid);
  }

  // ── Map grid ──────────────────────────────────────────────────────────
  function appendMapGrid(mapIndex) {
    const grid = document.createElement("div");
    grid.className = "card-grid map-grid";
    for (const m of ALL_MAPS) {
      const count = mapIndex.get(m.key)?.length ?? 0;
      const card  = document.createElement("div");
      card.className = "map-card";
      // Gradient stays as the backdrop, so a missing image needs no fallback
      // element — the card just looks the way it does today.
      card.style.background = m.bg;
      card.innerHTML = `
        <div class="map-card-inner">
          <div class="map-label">${esc(m.label)}</div>
          <div class="map-count">${count} video${count !== 1 ? "s" : ""}</div>
        </div>`;
      const art = mapImg(m.key);
      if (art) card.prepend(makeImageOrFallback(art, "map-card-img", () => document.createComment("")));
      card.addEventListener("click", () => navigate(state.tab, m.key));
      grid.appendChild(card);
    }
    app.appendChild(grid);
  }

  // ── Video grid with search ────────────────────────────────────────────
  const PAGE = 15;

  function appendVideoGrid(vids) {
    if (!vids.length) {
      app.insertAdjacentHTML("beforeend", `<div class="empty">No videos found.</div>`);
      return;
    }

    // Search bar — built via DOM to avoid HTML-parser issues with inline SVG
    const searchWrap = document.createElement("div");
    searchWrap.className = "video-search-wrap";

    const svgNS = "http://www.w3.org/2000/svg";
    const svg   = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", "search-icon");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    const circle = document.createElementNS(svgNS, "circle");
    circle.setAttribute("cx", "11"); circle.setAttribute("cy", "11"); circle.setAttribute("r", "8");
    const line = document.createElementNS(svgNS, "line");
    line.setAttribute("x1", "16.5"); line.setAttribute("y1", "16.5");
    line.setAttribute("x2", "21");   line.setAttribute("y2", "21");
    svg.appendChild(circle);
    svg.appendChild(line);

    const input = document.createElement("input");
    input.className    = "video-search";
    input.type         = "text";
    input.placeholder  = "Search videos…";
    input.autocomplete = "off";
    input.value        = state.q;   // seed from ?q= so deep links restore the search

    searchWrap.appendChild(svg);
    searchWrap.appendChild(input);
    app.appendChild(searchWrap);

    // Separate container so only the grid+pager is rebuilt on search/page change
    const container = document.createElement("div");
    app.appendChild(container);

    let page = 0;

    function renderGrid() {
      const q        = input.value.trim().toLowerCase();
      const filtered = q ? vids.filter(v => v.title.toLowerCase().includes(q)) : vids;
      const maxPage  = Math.max(0, Math.ceil(filtered.length / PAGE) - 1);
      page = Math.min(Math.max(0, page), maxPage);
      const slice = filtered.slice(page * PAGE, (page + 1) * PAGE);

      container.innerHTML = "";

      if (!slice.length) {
        container.insertAdjacentHTML("beforeend",
          `<div class="empty">No videos match your search.</div>`);
      } else {
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
            <div class="video-thumb">
              <img src="https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg"
                   width="320" height="180" loading="lazy" decoding="async" alt="">
              <button class="play-btn" type="button" aria-label="Play video">
                <svg viewBox="0 0 24 24" width="22" height="22"><path d="M8 5v14l11-7z" fill="#fff"/></svg>
              </button>
            </div>
            <div class="card-title">${esc(v.title)}</div>
            ${info ? `<div class="card-info">${info}</div>` : ""}`;

          // Load the real YouTube iframe only when the user clicks play
          const thumb = card.querySelector(".video-thumb");
          thumb.addEventListener("click", () => {
            const iframe = document.createElement("iframe");
            iframe.src = `https://www.youtube.com/embed/${encodeURIComponent(v.id)}?autoplay=1`;
            iframe.allow = "autoplay; fullscreen";
            iframe.allowFullscreen = true;
            iframe.referrerPolicy = "strict-origin-when-cross-origin";
            thumb.replaceWith(iframe);
          }, { once: true });

          // Bookmark button — DOM-built so it doesn't go through HTML parsing
          const bmBtn = document.createElement("button");
          bmBtn.className = "bookmark-btn" + (bookmarks.has(v.id) ? " bookmarked" : "");
          bmBtn.title     = bookmarks.has(v.id) ? "Remove bookmark" : "Save to bookmarks";
          bmBtn.appendChild(makeBookmarkIcon(bookmarks.has(v.id)));
          bmBtn.addEventListener("click", () => {
            const wasSaved = bookmarks.has(v.id);
            wasSaved ? bookmarks.delete(v.id) : bookmarks.add(v.id);
            saveBookmarks();
            bmBtn.classList.toggle("bookmarked", !wasSaved);
            bmBtn.title = bookmarks.has(v.id) ? "Remove bookmark" : "Save to bookmarks";
            bmBtn.replaceChildren(makeBookmarkIcon(bookmarks.has(v.id)));
            if (state.tab === "bookmarks") render();
          });
          card.appendChild(bmBtn);
          grid.appendChild(card);
        }
        container.appendChild(grid);
      }

      if (maxPage > 0) {
        const pager = document.createElement("div");
        pager.className = "pager";
        pager.innerHTML = `
          <button class="pager-prev" ${page === 0 ? "disabled" : ""}>‹ Prev</button>
          <span class="pager-info">${filtered.length ? page + 1 : 0} / ${maxPage + 1}</span>
          <button class="pager-next" ${page === maxPage ? "disabled" : ""}>Next ›</button>`;
        pager.querySelector(".pager-prev").addEventListener("click", () => { page--; renderGrid(); });
        pager.querySelector(".pager-next").addEventListener("click", () => { page++; renderGrid(); });
        container.appendChild(pager);
      }
    }

    input.addEventListener("input", () => {
      page = 0;
      renderGrid();
      syncSearchToUrl(input.value);
    });
    renderGrid();

    // Auto-focus the search input. preventScroll keeps back/forward
    // navigation from yanking the viewport down to the search bar.
    input.focus({ preventScroll: true });
  }

  // ── Boot ──────────────────────────────────────────────────────────────
  window.addEventListener("hashchange", applyHash);

  // Normalize a missing or malformed hash so every view has a copyable URL.
  const initial   = parseHash();
  const canonical = hashFor(initial.tab, initial.player ?? initial.map, initial.q);
  if (location.hash !== canonical) history.replaceState(null, "", canonical);

  applyHash();
})();
