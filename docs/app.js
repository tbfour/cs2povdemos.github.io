async function load() {
  const res = await fetch("data/videos.json");   // now points inside /docs
  const data = await res.json();

  const teamSet   = new Set(data.map(v => v.team).filter(Boolean));
  const playerSet = new Set(data.map(v => v.player));
  const mapSet    = new Set(data.map(v => v.map).filter(Boolean));

  const sel = (id,set) => {
    const el=document.getElementById(id);
    [...set].sort().forEach(v=>el.insertAdjacentHTML('beforeend',`<option>${v}</option>`));
    el.addEventListener('change', render);
    return el;
  };
  const teamSel=sel('team',teamSet), playerSel=sel('player',playerSet), mapSel=sel('map',mapSet);

  function render() {
    const t=teamSel.value,p=playerSel.value,m=mapSel.value;
    const wrap=document.getElementById('videos'); wrap.innerHTML='';
    data.filter(v=>(!t||v.team===t)&&(!p||v.player===p)&&(!m||v.map===m))
        .forEach(v=>{
          wrap.insertAdjacentHTML('beforeend',
            `<div>
               <iframe src="https://www.youtube.com/embed/${v.id}" allowfullscreen></iframe>
               <div><strong>${v.player}</strong> – ${v.map ?? 'unknown'} (${v.team ?? 'free-agent'})</div>
             </div>`);
        });
  }
  render();
}
load();
