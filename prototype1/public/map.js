// Live vacancy map (simulated data). Globe / flat world map with emerging vacancies,
// pulses and arcs to the user's location, coloured by career.
(function () {
  const CAREERS = [
    { n: 'AI Engineer', c: '#7FE3D3', t: ['python', 'ml', 'llm', 'cloud', 'math'], w: 1.3 },
    { n: 'Data Analyst', c: '#5AB0FF', t: ['sql', 'python', 'stats', 'bi', 'communication'], w: 1.2 },
    { n: 'Data Scientist', c: '#A08CFF', t: ['python', 'ml', 'stats', 'sql', 'math'], w: 1 },
    { n: 'Product Manager', c: '#FFB547', t: ['communication', 'strategy', 'analytics', 'ux'], w: 1.1 },
    { n: 'Software Engineer', c: '#4DD08A', t: ['code', 'cloud', 'python', 'systems'], w: 1.4 },
    { n: 'UX Designer', c: '#FF7EB6', t: ['ux', 'research', 'design', 'communication'], w: .8 },
    { n: 'Content Creator', c: '#FF6B5B', t: ['writing', 'video', 'social', 'design'], w: .9 },
    { n: 'Marketing Manager', c: '#F2E266', t: ['social', 'analytics', 'strategy', 'writing', 'communication'], w: .9 },
    { n: 'Cybersecurity Analyst', c: '#4FC3F7', t: ['systems', 'cloud', 'code', 'risk'], w: .8 },
    { n: 'DevOps Engineer', c: '#C6F06B', t: ['cloud', 'systems', 'code', 'python'], w: .8 },
  ];
  // [name, lon, lat, weight]
  const CITIES = [
    ['New York', -74.0, 40.7, 3], ['San Francisco', -122.4, 37.8, 3], ['Seattle', -122.3, 47.6, 2], ['Austin', -97.7, 30.3, 2],
    ['Chicago', -87.6, 41.9, 2], ['Boston', -71.1, 42.4, 2], ['Toronto', -79.4, 43.7, 2], ['Vancouver', -123.1, 49.3, 1],
    ['Mexico City', -99.1, 19.4, 1.5], ['São Paulo', -46.6, -23.5, 2], ['Buenos Aires', -58.4, -34.6, 1], ['Bogotá', -74.1, 4.7, 1],
    ['London', -0.1, 51.5, 3], ['Dublin', -6.3, 53.3, 1.5], ['Paris', 2.35, 48.9, 2], ['Berlin', 13.4, 52.5, 2.5],
    ['Amsterdam', 4.9, 52.4, 2], ['Stockholm', 18.1, 59.3, 1], ['Warsaw', 21.0, 52.2, 1.5], ['Madrid', -3.7, 40.4, 1.5],
    ['Lisbon', -9.1, 38.7, 1], ['Zurich', 8.5, 47.4, 1.2], ['Istanbul', 29.0, 41.0, 1.5], ['Tel Aviv', 34.8, 32.1, 1.5],
    ['Dubai', 55.3, 25.2, 2], ['Riyadh', 46.7, 24.7, 1], ['Cairo', 31.2, 30.0, 1], ['Lagos', 3.4, 6.5, 1.2],
    ['Nairobi', 36.8, -1.3, 1.2], ['Cape Town', 18.4, -33.9, 1], ['Almaty', 76.9, 43.2, 1.5], ['Astana', 71.4, 51.2, 1.2],
    ['Tashkent', 69.2, 41.3, 1], ['Bengaluru', 77.6, 13.0, 3], ['Mumbai', 72.9, 19.1, 2], ['Delhi', 77.2, 28.6, 2],
    ['Singapore', 103.8, 1.35, 2.5], ['Jakarta', 106.8, -6.2, 1.2], ['Bangkok', 100.5, 13.8, 1.2], ['Ho Chi Minh City', 106.7, 10.8, 1],
    ['Shanghai', 121.5, 31.2, 2], ['Shenzhen', 114.1, 22.5, 2], ['Hong Kong', 114.2, 22.3, 1.5], ['Seoul', 127.0, 37.6, 2],
    ['Tokyo', 139.7, 35.7, 2.5], ['Sydney', 151.2, -33.9, 1.8], ['Melbourne', 145.0, -37.8, 1.2], ['Auckland', 174.8, -36.8, .8],
  ];
  const HOMES = ['New York', 'San Francisco', 'London', 'Berlin', 'Almaty', 'Astana', 'Dubai', 'Bengaluru', 'Singapore', 'Tokyo', 'São Paulo'];

  const cv = document.getElementById('globe'), ctx = cv.getContext('2d');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const S = {
    view: 'globe', rot: [70, -18], career: 'Data Analyst', home: 'New York', off: new Set(),
    events: [], arcs: [], land: null, w: 0, h: 0, dragging: false, total: 18240 + Math.floor(Math.random() * 900), fit: 0,
    perCareer: Object.fromEntries(CAREERS.map(c => [c.n, 0])), perCity: {}, lastFeed: 0,
  };
  const byName = Object.fromEntries(CAREERS.map(c => [c.n, c]));
  const cityByName = Object.fromEntries(CITIES.map(c => [c[0], c]));
  const graticule = d3.geoGraticule10();

  // ---------- controls ----------
  const $ = id => document.getElementById(id);
  $('mCareer').innerHTML = CAREERS.map(c => `<option${c.n === S.career ? ' selected' : ''}>${c.n}</option>`).join('');
  $('mHome').innerHTML = HOMES.map(h => `<option${h === S.home ? ' selected' : ''}>${h}</option>`).join('');
  $('mCareer').onchange = e => { S.career = e.target.value; $('mFeed').innerHTML = ''; S.fit = 0; };
  $('mHome').onchange = e => { S.home = e.target.value; const c = cityByName[S.home]; S.rot = [-c[1], -c[2] * .5]; };
  document.querySelectorAll('#mView button').forEach(b => b.onclick = () => {
    S.view = b.dataset.v; document.querySelectorAll('#mView button').forEach(x => x.classList.toggle('on', x === b));
  });
  function legend() {
    $('mLegend').innerHTML = CAREERS.map(c => `<button data-c="${c.n}" class="${S.off.has(c.n) ? 'off' : ''}"><span class="sw" style="color:${c.c}"></span>${c.n}<em>${S.perCareer[c.n]}</em></button>`).join('');
    document.querySelectorAll('#mLegend button').forEach(b => b.onclick = () => { const n = b.dataset.c; S.off.has(n) ? S.off.delete(n) : S.off.add(n); legend(); });
  }
  legend();

  // ---------- data ----------
  fetch('https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/land-110m.json').then(r => r.json())
    .then(t => { S.land = topojson.feature(t, t.objects.land); }).catch(() => {});

  const pick = (arr, wf) => { const tot = arr.reduce((a, x) => a + wf(x), 0); let r = Math.random() * tot; for (const x of arr) { r -= wf(x); if (r <= 0) return x; } return arr[0]; };
  function fitScore(a, b) {
    const A = new Set(byName[a].t), B = new Set(byName[b].t);
    const inter = [...A].filter(x => B.has(x)).length, uni = new Set([...A, ...B]).size;
    return Math.max(18, Math.min(99, Math.round(30 + 65 * inter / uni + (Math.random() * 14 - 7))));
  }
  function spawn(now) {
    const career = pick(CAREERS, c => c.w * (c.n === S.career ? 1.8 : 1));
    const city = pick(CITIES, c => c[3]);
    const lon = city[1] + (Math.random() - .5) * 1.6, lat = city[2] + (Math.random() - .5) * 1.2;
    const fit = fitScore(S.career, career.n);
    const ev = { lon, lat, career: career.n, color: career.c, fit, city: city[0], born: now, life: 3200 + Math.random() * 1600 };
    S.events.push(ev);
    S.total++; S.perCareer[career.n]++; S.perCity[city[0]] = (S.perCity[city[0]] || 0) + 1;
    if (fit >= 80) {
      S.fit++;
      if (city[0] !== S.home) { const h = cityByName[S.home]; S.arcs.push({ a: [lon, lat], b: [h[1], h[2]], color: career.c, career: career.n, born: now, dur: 1400 }); }
    }
    if (fit >= 60 && !S.off.has(career.n) && now - S.lastFeed > 650) { S.lastFeed = now; feed(ev); }
  }
  function feed(ev) {
    const li = document.createElement('li');
    li.innerHTML = `<span class="sw" style="color:${ev.color}"></span><span>${ev.career}<small>${ev.city}</small></span><b class="${ev.fit >= 80 ? 'hi' : ''}">${ev.fit}%</b>`;
    const ul = $('mFeed'); ul.prepend(li); while (ul.children.length > 16) ul.lastChild.remove();
  }
  let statT = 0;
  function stats(now) {
    if (now - statT < 400) return; statT = now;
    $('sTotal').textContent = S.total.toLocaleString('en-US');
    $('sFit').textContent = S.fit.toLocaleString('en-US');
    const top = Object.entries(S.perCity).sort((a, b) => b[1] - a[1])[0];
    $('sTop').textContent = top ? top[0] : '—';
    document.querySelectorAll('#mLegend em').forEach((e, i) => e.textContent = S.perCareer[CAREERS[i].n]);
  }

  // ---------- projection ----------
  function resize() {
    const r = cv.getBoundingClientRect(), dpr = Math.min(devicePixelRatio || 1, 2);
    S.w = r.width; S.h = r.height; cv.width = r.width * dpr; cv.height = r.height * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  addEventListener('resize', resize);
  function projection() {
    const { w, h } = S, narrow = w < 980;
    const cx = narrow ? w / 2 : w * 0.47, cy = narrow ? h * 0.52 : h * 0.54;
    if (S.view === 'globe') {
      const R = Math.min(w * (narrow ? .44 : .3), h * .38);
      return d3.geoOrthographic().scale(R).translate([cx, cy]).rotate(S.rot).clipAngle(90);
    }
    return d3.geoNaturalEarth1().fitExtent([[narrow ? 20 : 250, narrow ? 200 : 110], [w - (narrow ? 20 : 310), h - (narrow ? 260 : 80)]], { type: 'Sphere' });
  }
  const center = () => [-S.rot[0], -S.rot[1]];
  const visible = p => S.view !== 'globe' || d3.geoDistance(p, center()) < Math.PI / 2 - 0.02;

  // ---------- drag ----------
  let last = null;
  cv.addEventListener('pointerdown', e => { if (S.view !== 'globe') return; S.dragging = true; last = [e.clientX, e.clientY]; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener('pointermove', e => {
    if (!S.dragging) return;
    S.rot[0] += (e.clientX - last[0]) * .3; S.rot[1] = Math.max(-60, Math.min(60, S.rot[1] - (e.clientY - last[1]) * .3)); last = [e.clientX, e.clientY];
  });
  cv.addEventListener('pointerup', () => S.dragging = false);

  // ---------- render ----------
  function drawArc(proj, arc, now) {
    const t = Math.min(1, (now - arc.born) / arc.dur), fade = now - arc.born > arc.dur ? 1 - (now - arc.born - arc.dur) / 900 : 1;
    if (fade <= 0) return false;
    const interp = d3.geoInterpolate(arc.a, arc.b), dist = d3.geoDistance(arc.a, arc.b), N = 48;
    const pts = [];
    for (let i = 0; i <= N; i++) {
      const k = i / N, p = interp(k), lift = Math.sin(Math.PI * k) * dist * 0.18;
      let xy;
      if (S.view === 'globe') {
        if (d3.geoDistance(p, center()) > Math.PI / 2) { pts.push(null); continue; }
        const R = proj.scale(); xy = proj.scale(R * (1 + lift))(p); proj.scale(R);
      } else { xy = proj(p); if (xy) xy[1] -= lift * S.h * 0.5; }
      pts.push(xy);
    }
    const head = Math.floor(t * N);
    ctx.lineCap = 'round';
    const seg = (from, to, alpha, width) => {
      ctx.beginPath(); let pen = false, prev = null;
      for (let i = from; i <= to; i++) {
        const p = pts[i];
        if (!p || (prev && Math.abs(p[0] - prev[0]) > S.w / 3)) { pen = false; prev = p; continue; }
        pen ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); pen = true; prev = p;
      }
      ctx.globalAlpha = alpha * fade; ctx.lineWidth = width; ctx.strokeStyle = arc.color; ctx.stroke();
    };
    seg(0, head, .22, 1.2);
    seg(Math.max(0, head - 10), head, .95, 2);
    const hp = pts[head];
    if (hp && t < 1) { ctx.globalAlpha = fade; ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(hp[0], hp[1], 2.2, 0, 7); ctx.fill(); }
    ctx.globalAlpha = 1;
    return true;
  }

  let prevT = performance.now(), acc = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(100, now - prevT); prevT = now;
    if (document.getElementById('v-main').classList.contains('hide') || document.hidden) return;
    if (!S.w) resize();
    acc += dt; const every = reduce ? 900 : 190;
    while (acc > every) { acc -= every; spawn(now); }
    if (S.view === 'globe' && !S.dragging && !reduce) S.rot[0] += dt * 0.006;

    const proj = projection(), path = d3.geoPath(proj, ctx), { w, h } = S;
    ctx.clearRect(0, 0, w, h);

    // sphere + atmosphere
    if (S.view === 'globe') {
      const [cx, cy] = proj.translate(), R = proj.scale();
      const g = ctx.createRadialGradient(cx, cy, R * .9, cx, cy, R * 1.25);
      g.addColorStop(0, 'rgba(62,143,134,.35)'); g.addColorStop(1, 'rgba(62,143,134,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R * 1.25, 0, 7); ctx.fill();
    }
    ctx.beginPath(); path({ type: 'Sphere' });
    const sg = ctx.createLinearGradient(0, 0, 0, h); sg.addColorStop(0, '#0F2228'); sg.addColorStop(1, '#0A161A');
    ctx.fillStyle = sg; ctx.fill();
    ctx.beginPath(); path(graticule); ctx.strokeStyle = 'rgba(127,148,153,.08)'; ctx.lineWidth = .7; ctx.stroke();
    if (S.land) {
      ctx.beginPath(); path(S.land); ctx.fillStyle = '#18323A'; ctx.fill();
      ctx.strokeStyle = 'rgba(108,191,180,.35)'; ctx.lineWidth = .6; ctx.stroke();
    }
    ctx.beginPath(); path({ type: 'Sphere' }); ctx.strokeStyle = 'rgba(108,191,180,.25)'; ctx.lineWidth = 1; ctx.stroke();

    ctx.globalCompositeOperation = 'lighter';
    // arcs
    S.arcs = S.arcs.filter(a => {
      if (S.off.has(a.career)) return now - a.born < a.dur + 900;
      return drawArc(proj, a, now);
    });
    // vacancy pulses
    const labels = [];
    S.events = S.events.filter(ev => {
      const age = (now - ev.born) / ev.life;
      if (age >= 1) return false;
      if (S.off.has(ev.career) || !visible([ev.lon, ev.lat])) return true;
      const p = proj([ev.lon, ev.lat]); if (!p) return true;
      const hi = ev.fit >= 80, base = hi ? 3.2 : 2.2;
      const glow = ctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], base * 5);
      glow.addColorStop(0, ev.color); glow.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.globalAlpha = (1 - age) * (hi ? .9 : .5); ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(p[0], p[1], base * 5, 0, 7); ctx.fill();
      ctx.globalAlpha = 1 - age; ctx.fillStyle = ev.color; ctx.beginPath(); ctx.arc(p[0], p[1], base * (age < .1 ? age * 10 : 1), 0, 7); ctx.fill();
      for (const k of [0, .35]) {
        const a2 = age - k; if (a2 <= 0) continue;
        ctx.globalAlpha = Math.max(0, (1 - a2) * .8); ctx.strokeStyle = ev.color; ctx.lineWidth = hi ? 1.6 : 1;
        ctx.beginPath(); ctx.arc(p[0], p[1], 3 + a2 * (hi ? 30 : 18), 0, 7); ctx.stroke();
      }
      if (ev.fit >= 88 && age < .75) labels.push([p, ev, age]);
      return true;
    });
    ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1;

    // home marker
    const hc = cityByName[S.home];
    if (visible([hc[1], hc[2]])) {
      const p = proj([hc[1], hc[2]]), pulse = (now / 1400) % 1;
      ctx.strokeStyle = '#D9A441'; ctx.lineWidth = 2; ctx.globalAlpha = 1 - pulse;
      ctx.beginPath(); ctx.arc(p[0], p[1], 6 + pulse * 16, 0, 7); ctx.stroke(); ctx.globalAlpha = 1;
      ctx.fillStyle = '#D9A441'; ctx.beginPath(); ctx.arc(p[0], p[1], 4.5, 0, 7); ctx.fill();
      ctx.font = '600 12px Onest, system-ui'; ctx.fillStyle = '#F5D79A'; ctx.fillText('You · ' + S.home, p[0] + 10, p[1] + 4);
    }
    // labels for top matches
    ctx.font = '500 11px Onest, system-ui';
    labels.slice(-3).forEach(([p, ev, age]) => {
      const txt = `${ev.career} · ${ev.city} · ${ev.fit}%`, tw = ctx.measureText(txt).width;
      ctx.globalAlpha = Math.min(1, (.75 - age) * 4);
      ctx.fillStyle = 'rgba(11,20,24,.85)'; ctx.strokeStyle = ev.color; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.roundRect ? ctx.roundRect(p[0] + 10, p[1] - 24, tw + 14, 20, 6) : ctx.rect(p[0] + 10, p[1] - 24, tw + 14, 20); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#fff'; ctx.fillText(txt, p[0] + 17, p[1] - 10);
    });
    ctx.globalAlpha = 1;
    stats(now);
  }
  resize(); requestAnimationFrame(frame);
  window.TirekMap = { resize };
})();
