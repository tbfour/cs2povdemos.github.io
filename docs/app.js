async function load() {
  // 1. Fetch catalogue ----------------------------------------------------
  const res  = await fetch("data/videos.json");
  const data = await res.json();

  // 2. Build filter blocks -------------------------------------------------
  const makeFilter = (key, label, set) => {
    const container = document.createElement("div");
    container.className = "filter";

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = `Search ${label}`;
    input.dataset.key = key;
    input.setAttribute("list", `${key}List`);

    const list = document.createElement("datalist");
    list.id = `${key}List`;
    [...set].sort().forEach(v => list.insertAdjacentHTML("beforeend", `<option value="${v}">`));

    container.append(input, list);
    document.querySelector(".filters").appendChild(container);
    return input;
  };

  const teamInput   = makeFilter("team",   "Team",   new Set(data.map(v => v.team)));
  const playerInput = makeFilter("player", "Player", new Set(data.map(v => v.player)));
  const mapInput    = makeFilter("map",    "Map",    new Set(data.map(v => v.map)));

  // 3. Pagination + render -------------------------------------------------
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

  [teamInput, playerInput, mapInput].forEach(inp =>
    inp.addEventListener("input", () => { page = 0; render(); }));

  function render() {
    const t = teamInput.value.trim();
    const p = playerInput.value.trim();
    const m = mapInput.value.trim();

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
      wrap.insertAdjacentHTML("beforeend",
        `<div class="card">
           <iframe src="https://www.youtube.com/embed/${v.id}" allowfullscreen></iframe>
           <div class="card-info">${v.title}</div>
         </div>`);
    });

    pageInfo.textContent = `${page + 1} / ${maxPage + 1}`;
    prevBtn.disabled = page === 0;
    nextBtn.disabled = page === maxPage;
  }
  render();

  // 4. Theme toggle --------------------------------------------------------
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
