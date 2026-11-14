// tirek — prototype 2: landing → auth → profile → report → roadmap → interview → feedback
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const API = (window.API_BASE || '').replace(/\/$/, '');
const k$ = n => n == null ? '—' : '$' + (n >= 1000 ? Math.round(n / 1000) + 'k' : Math.round(n));
let tt; function toast(t) { const e = $('#toast'); e.textContent = t; e.classList.add('on'); clearTimeout(tt); tt = setTimeout(() => e.classList.remove('on'), 2600); }
const spin = t => `<div class="loading"><span class="spin"></span><b>${esc(t)}</b><span class="sm mu" id="loadStep"></span></div>`;

async function api(path, body) {
  let r;
  try { r = await fetch(API + path, { credentials: 'include', ...(body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) }); }
  catch (e) { throw new Error('Cannot reach the server. Check your connection or the API address (frontend/vercel.json).'); }
  const j = await r.json().catch(() => null);
  if (r.status === 401 && path !== '/api/login' && path !== '/api/me') { ME = null; location.hash = '#/login'; }
  if (!j) throw new Error(`The API did not answer correctly (HTTP ${r.status}). Check that /api/health works and that vercel.json points to your Railway domain.`);
  if (!r.ok) throw new Error((j.error || j.message || 'Request failed') + ` (HTTP ${r.status})` + (r.status >= 500 ? ' — the server may be restarting, try again in a minute.' : ''));
  return j;
}
const track = name => api('/api/event', { name }).catch(() => {});

let ME = null, ROLES = [], CV = { text: '', name: '' }, SEL = new Set(), ONLY_GAPS = true, PICKS = {};
const TABS = [['profile', 'Profile'], ['report', 'Report'], ['roadmap', 'Roadmap'], ['interview', 'AI interview'], ['feedback', 'Feedback']];
const PUBLIC = ['landing', 'login', 'signup', 'privacy'], VIEWS = [...PUBLIC, ...TABS.map(t => t[0])];
const SALARIES = ['Under $50k', '$50k–$75k', '$75k–$100k', '$100k–$130k', '$130k–$160k', '$160k–$200k', '$200k+'];
const HOURS = ['1–2 h / week', '3–5 h / week', '6–10 h / week', '10+ h / week'];

// ---------- routing ----------
function route() {
  const h = location.hash.replace(/^#\/?/, '');
  let view = h.startsWith('app/') ? h.slice(4) : (h || 'landing');
  if (!VIEWS.includes(view)) view = 'landing';
  if (!ME && !PUBLIC.includes(view)) { location.hash = '#/login'; return; }
  if (ME && PUBLIC.includes(view) && view !== 'privacy') { location.hash = '#/app/' + (ME.report ? 'report' : 'profile'); return; }
  VIEWS.forEach(v => $('#v-' + v).classList.toggle('hide', v !== view));
  const app = !PUBLIC.includes(view) || (view === 'privacy' && !!ME);
  ['#nav', '#logout', '#who', '#mus'].forEach(s => $(s).classList.toggle('hide', !app));
  $('#vol').classList.toggle('hide', !app || !play);
  if (app) {
    $('#who').textContent = ME.user.name;
    $('#nav').innerHTML = TABS.map(([k, n]) => `<button class="${k === view ? 'on' : ''}" data-t="${k}">${n}${done(k) ? '<i>●</i>' : ''}</button>`).join('');
    $$('#nav button').forEach(b => b.onclick = () => location.hash = '#/app/' + b.dataset.t);
  }
  if (view === 'landing') window.TirekMap && TirekMap.resize();
  ({ profile: renderProfile, report: renderReport, roadmap: renderRoadmap, interview: renderInterview, feedback: renderFeedback })[view]?.();
  scrollTo(0, 0);
}
const done = k => ({ profile: !!ME.report, report: !!ME.roadmap, roadmap: !!ME.roadmap, interview: !!ME.result, feedback: ME.feedbackDone })[k];
addEventListener('hashchange', route);

// ---------- auth ----------
async function authSubmit(e, path) {
  e.preventDefault(); const f = e.target, b = f.querySelector('button[type=submit]'), err = f.querySelector('.ferr');
  err.textContent = ''; b.disabled = true;
  const data = Object.fromEntries(new FormData(f).entries());
  f.querySelectorAll('input[type=checkbox]').forEach(c => data[c.name] = c.checked);
  try { await api(path, data); ME = await api('/api/me'); f.reset(); location.hash = '#/app/profile'; toast('Welcome, ' + ME.user.name); }
  catch (x) { err.textContent = x.message; }
  b.disabled = false;
}
$('#loginForm').onsubmit = e => authSubmit(e, '/api/login');
$('#signupForm').onsubmit = e => authSubmit(e, '/api/signup');
$('#logout').onclick = async () => { await api('/api/logout', {}).catch(() => {}); ME = null; CV = { text: '', name: '' }; SEL.clear(); location.hash = '#/'; };

// ---------- profile ----------
const SAMPLE = `Maya R. — Data Analyst, New York, NY. 4 years of experience.
Data Analyst at a retail marketplace (2022–present): SQL queries in PostgreSQL on orders and customer behavior; Tableau dashboards for merchandising; automated monthly reporting with Python (pandas), saving 6 hours per month; presented findings to stakeholders in leadership reviews.
Junior Analyst at a logistics company (2020–2022): advanced Excel modeling with pivot tables, tracked funnel and retention metrics.
Education: BA Economics, CUNY. Preferred: hybrid in New York, $110k+.`;
function renderProfile() {
  const inp = ME.input || {}, opt = (arr, v) => arr.map(x => `<option ${x === v ? 'selected' : ''}>${esc(x)}</option>`).join('');
  $('#v-profile').innerHTML = `
  <h1 style="margin:10px 0 18px">Your profile</h1>
  ${ME.report ? '<p class="sm mu" style="margin:-8px 0 16px">A new report saves your current one to History as a PDF.</p>' : ''}
  <div class="grid2">
    <div class="card"><h2>CV</h2>
      <label class="drop ${CV.text ? 'ok' : ''}">${CV.text ? `✓ ${esc(CV.name)}` : '<b>Upload PDF or .txt</b>'}<input type="file" id="cvFile" accept="application/pdf,.txt,text/plain" hidden></label>
      <div class="row" style="margin-top:12px"><button class="btn ghost small" id="sample">Try a sample CV</button>${CV.text ? '<button class="btn ghost small" id="clearCv">Remove</button>' : ''}</div>
      ${!CV.text && ME.savedCv ? `<label class="row sm" style="margin-top:12px"><input type="checkbox" id="useSaved" checked> Use my saved CV (${esc(ME.savedCv)})</label>` : ''}
      <div id="cvErr"></div>
    </div>
    <div class="card"><h2>About you</h2>
      <textarea id="about" placeholder="Experience, skills, preferred location, salary, Remote / Hybrid / Office…">${esc(inp.about || '')}</textarea>
    </div>
  </div>
  <div class="card"><div class="grid4">
      <label class="fld">Current role<select id="curRole">${opt([...ROLES, 'Other'], inp.currentRole || 'Data Analyst')}</select></label>
      <label class="fld">Target role<select id="tgtRole">${opt(ROLES, inp.targetRole || 'Data Scientist')}</select></label>
      <label class="fld">Target salary / year<select id="tgtSal">${opt(SALARIES, inp.targetSalary || '$100k–$130k')}</select></label>
      <label class="fld">Study time<select id="hours">${opt(HOURS, inp.studyHours || '3–5 h / week')}</select></label>
    </div><div id="pErr"></div>
    <div class="row" style="margin-top:18px;justify-content:flex-end"><button class="btn blue big" id="gen">Generate career report →</button></div>
  </div>
  ${privacyCard()}`;
  bindPrivacy();
  $('#cvFile').onchange = readCv;
  $('#sample').onclick = () => { CV = { text: SAMPLE, name: 'sample-cv.txt' }; keepInput(); renderProfile(); };
  $('#clearCv') && ($('#clearCv').onclick = () => { CV = { text: '', name: '' }; keepInput(); renderProfile(); });
  $('#gen').onclick = generate;
}
function keepInput() { ME.input = { ...(ME.input || {}), about: $('#about').value, currentRole: $('#curRole').value, targetRole: $('#tgtRole').value, targetSalary: $('#tgtSal').value, studyHours: $('#hours').value }; }
async function readCv(e) {
  const f = e.target.files[0]; if (!f) return; keepInput();
  const fail = m => { $('#cvErr').innerHTML = `<div class="err">${esc(m)}</div>`; };
  if (f.size > 5e6) return fail('File is over 5 MB.');
  try {
    let text = '';
    if (f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')) {
      if (!window.pdfjsLib) return fail('PDF reader unavailable — paste your CV into “About you”.');
      pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      const pdf = await pdfjsLib.getDocument({ data: await f.arrayBuffer() }).promise;
      for (let i = 1; i <= Math.min(pdf.numPages, 8); i++) text += (await (await pdf.getPage(i)).getTextContent()).items.map(x => x.str).join(' ') + '\n';
    } else text = await f.text();
    if (text.trim().length < 50) return fail('No text found (scanned PDF?). Paste your CV into “About you”.');
    CV = { text: text.trim(), name: f.name }; renderProfile();
  } catch (x) { fail('Could not read this file.'); }
}
async function generate() {
  keepInput(); const i = ME.input, useSaved = !CV.text && !!$('#useSaved')?.checked;
  if ((CV.text + i.about).trim().length < 40 && !useSaved) { $('#pErr').innerHTML = '<div class="err">Upload a CV or write a few sentences about you.</div>'; return; }
  track('report_started');
  $('#v-profile').innerHTML = `<div class="card">${spin('Building your report')}</div>`;
  const steps = ['Reading your profile', 'Matching 100 real US vacancies', 'Calculating risk and market value', 'Finding alternative roles'];
  let k = 0; $('#loadStep').textContent = steps[k++];
  const iv = setInterval(() => { const e = $('#loadStep'); if (e) e.textContent = steps[Math.min(k++, steps.length - 1)]; }, 3000);
  try {
    await api('/api/report', { cvText: CV.text, cvName: CV.name, useSavedCv: useSaved, about: i.about, currentRole: i.currentRole, targetRole: i.targetRole, targetSalary: i.targetSalary, studyHours: i.studyHours });
    ME = await api('/api/me'); SEL.clear(); clearInterval(iv); location.hash = '#/app/report'; route();
  } catch (x) { clearInterval(iv); renderProfile(); $('#pErr').innerHTML = `<div class="err">${esc(x.message)}</div>`; }
}

// ---------- privacy controls (consent, export, delete) ----------
function privacyCard() {
  const c = ME.user.consent || {};
  return `<div class="card"><div class="row between"><h2 style="margin:0">Your data</h2><a class="sm" href="#/privacy">Privacy policy</a></div>
    <label class="row sm" style="margin-top:12px"><input type="checkbox" data-consent="store_cv" ${c.storeCv ? 'checked' : ''}> Keep my CV text so I can reuse it (auto-deleted after 90 days)</label>
    <label class="row sm" style="margin-top:6px"><input type="checkbox" data-consent="research" ${c.research ? 'checked' : ''}> Use my anonymised results to improve tirek</label>
    <div class="row" style="margin-top:14px"><a class="btn ghost small" href="${API}/api/me/export">Download my data</a><button class="btn ghost small" id="delAcc">Delete my account</button></div></div>`;
}
function bindPrivacy() {
  $$('[data-consent]').forEach(c => c.onchange = async () => {
    try { ME.user = (await api('/api/me/consent', { kind: c.dataset.consent, value: c.checked })).user; if (!c.checked && c.dataset.consent === 'store_cv') ME.savedCv = null; toast(c.checked ? 'Saved' : 'Consent withdrawn'); keepScroll(renderProfile); }
    catch (x) { toast(x.message); c.checked = !c.checked; }
  });
  $('#delAcc').onclick = () => {
    $('#delAcc').closest('.row').insertAdjacentHTML('afterend', `<div class="err" id="delBox"><b>This permanently deletes your account, CV, reports and history.</b> Feedback stays only as anonymous text.
      <div class="row" style="margin-top:10px"><input type="password" id="delPw" placeholder="Your password" style="max-width:240px;background:#fff;color:#111317"><button class="btn small" id="delGo">Delete forever</button><button class="btn ghost small" id="delNo">Cancel</button></div></div>`);
    $('#delAcc').disabled = true;
    $('#delNo').onclick = () => { $('#delBox').remove(); $('#delAcc').disabled = false; };
    $('#delGo').onclick = async () => {
      try { await api('/api/me/delete', { password: $('#delPw').value }); ME = null; CV = { text: '', name: '' }; location.hash = '#/'; toast('Your account and data were deleted'); }
      catch (x) { toast(x.message); }
    };
  };
}

// ---------- report ----------
const empty = (msg, to, label) => `<div class="card empty">${esc(msg)}<br><br><a class="btn blue" href="#/app/${to}">${esc(label)}</a></div>`;
const payTxt = s => s ? `${k$(s.min)}–${k$(s.max)}` : '';
function spark(points) {
  if (points.length < 2) return '<p class="sm mu">Upload an updated CV later — your progress will appear here.</p>';
  const W = 300, H = 70, x = i => 10 + i * (W - 20) / (points.length - 1), y = v => H - 8 - (v / 100) * (H - 16);
  const line = (key, col) => `<polyline fill="none" stroke="${col}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${points.map((p, i) => `${x(i)},${y(p[key] ?? 0)}`).join(' ')}"/>` +
    points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p[key] ?? 0)}" r="4" fill="${col}"/>`).join('');
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${line('score', 'var(--yellow)')}${line('readiness', 'var(--blue)')}</svg>
    <div class="row sm mu"><span><span class="sw" style="color:var(--yellow);display:inline-block"></span> Risk</span><span><span class="sw" style="color:var(--blue);display:inline-block"></span> Readiness</span>
    <span style="margin-left:auto">${points.map(p => k$(p.valueMax)).join(' → ')} max value</span></div>`;
}
function renderReport() {
  const R = ME.report, v = $('#v-report');
  if (!R) { v.innerHTML = empty('No report yet.', 'profile', 'Fill in your profile →'); return; }
  const rk = R.risk, V = R.value || {}, H = ME.history || { items: [], progress: [] };
  const vac = R.vacancies.filter(j => !ONLY_GAPS || j.missing.length);
  v.innerHTML = `
  <div class="row between" style="margin:10px 0 18px"><h1 style="margin:0">${esc(R.currentRole)} → ${esc(R.targetRole)}</h1>
    <a class="btn ghost small" href="${API}/api/report.pdf">Download PDF</a></div>
  <div class="hero3">
    <div class="blk green"><div class="lbl">Your market value now</div>
      <div class="big">${V.min ? `${k$(V.min)} – ${k$(V.max)}` : 'Not enough data'}</div>
      <div class="sub">per year · median ${k$(V.median)} · ${V.n || 0} real postings you match</div>
      ${V.best?.length ? `<details style="margin-top:12px"><summary>Best-paid matches</summary>${V.best.map(b => `<div class="sm"><a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.title)} · ${esc(b.company)}</a> — ${payTxt(b.salaryYear)}</div>`).join('')}<div class="sm" style="margin-top:6px;opacity:.85">Based on ${esc(V.basis)}.</div></details>` : ''}
    </div>
    <div class="blk yellow"><div class="lbl">Career risk</div><div class="big">${rk.score}<span style="font-size:20px">/100</span></div>
      <div class="sub">${esc(rk.level)}</div><div class="meter"><i style="width:${rk.score}%"></i></div>
      <details style="margin-top:12px"><summary>What affects it</summary>${rk.factors.map(f => `<div class="sm" style="margin-bottom:6px"><b>${Math.round(f.weight * 100)}% ${esc(f.name)}</b> · ${f.contribution} pts<br>${esc(f.explanation)}</div>`).join('')}<div class="sm" style="opacity:.8">${esc(rk.formula)} — fixed formula, demo weights.</div></details>
    </div>
    <div class="blk blue"><div class="lbl">Ready for ${esc(R.targetRole)}</div><div class="big">${V.readiness ?? '—'}%</div>
      <div class="sub">${V.potential ? `Potential: up to ${k$(V.potential.max)}/yr` : ''}</div><div class="meter"><i style="width:${V.readiness || 0}%"></i></div>
    </div>
  </div>
  <div class="grid2" style="margin-top:16px">
    <div class="card"><h2>Progress</h2>${spark(H.progress)}</div>
    <div class="card"><h2>History</h2>${H.items.length ? H.items.map(h => `<div class="hist"><div><b>${esc(h.createdAt.slice(0, 10))}</b> <span class="sm mu">· risk ${h.score} · ${h.valueMin ? payTxt({ min: h.valueMin, max: h.valueMax }) : '—'}</span></div><a class="btn ghost small" href="${API}/api/history/${esc(h.id)}.pdf">PDF</a></div>`).join('') : '<p class="sm mu">Previous reports are saved here as PDFs when you upload a new CV.</p>'}</div>
  </div>
  <div class="grid2">
    <div class="card"><h2>Skills</h2>
      ${[['Growing', 'g', R.growing], ['Stable', 'b', R.stable], ['Declining', 'y', R.declining]].map(([t, c, xs]) => `<div class="trow"><span class="chip ${c}" style="text-align:center">${t}</span><div>${xs.map(x => `<span class="chip o" title="${esc(x.reason)}">${esc(x.skill)}</span>`).join('') || '<span class="mu">—</span>'}</div></div>`).join('')}
      <details><summary>Your detected skills</summary>${R.skills.map(s => `<span class="chip">${esc(s)}</span>`).join('')}</details>
    </div>
    <div class="card"><h2>Other directions</h2>
      ${R.alternatives.map(a => `<div class="alt"><div><b>${esc(a.role)}</b><div class="sm mu">${a.salary ? 'median ' + k$(a.salary.median) + '/yr' : 'salary not stated'} · ${a.vacancies} jobs</div></div><div class="bar"><i style="width:${a.match}%"></i></div><b>${a.match}%</b></div>
        <details style="margin:-4px 0 8px"><summary>Details</summary><div class="sm">
          ${a.missingSkills.length ? `<div>Missing: ${a.missingSkills.map(s => `<span class="chip y">${esc(s)}</span>`).join('')}</div>` : ''}
          <div class="mu">${esc(a.time)} · ${esc(a.difficulty)} difficulty</div>
          <div class="links" style="margin-top:6px">${a.courses.map(c => `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title)} ↗</a>`).join('')}</div></div></details>`).join('')}
    </div>
  </div>
  <div class="card"><h2>90-day protection plan</h2>
    ${R.protectionPlan.map((p, i) => `<div class="step"><div class="n">${i + 1}</div><div><b>${esc(p.focus)}</b> <span class="sm mu">${esc(p.period)}</span><details><summary>How</summary><div class="sm">${esc(p.actions)}<br><b>Result:</b> ${esc(p.result)}</div></details></div></div>`).join('')}
  </div>
  <div class="row between" style="margin:26px 4px 12px"><h2 style="margin:0">Vacancies & salaries</h2>
    <label class="row sm mu"><input type="checkbox" id="onlyGaps" ${ONLY_GAPS ? 'checked' : ''}> Only where I lack skills</label></div>
  ${vac.map(j => `<div class="vac ${SEL.has(j.id) ? 'sel' : ''}"><input type="checkbox" data-j="${esc(j.id)}" ${SEL.has(j.id) ? 'checked' : ''} aria-label="Select ${esc(j.title)}">
    <div><b>${esc(j.title)}</b><div class="sm mu">${esc(j.company)} · ${esc(j.location)}</div>
      <div style="margin-top:8px"><span class="fit ${j.fit >= 60 ? 'hi' : j.fit >= 35 ? 'mid' : ''}">${j.fit}% fit</span>
      ${j.missing.length ? `<details style="display:inline-block;margin-left:8px"><summary>${j.missing.length} skills to learn</summary>${j.missing.map(s => `<span class="chip y">${esc(s)}</span>`).join('')}</details>` : ''}</div></div>
    <div style="text-align:right"><div class="pay">${j.salaryYear ? payTxt(j.salaryYear) + '<small> /yr</small>' : '<small>salary not stated</small>'}</div><a class="sm" href="${esc(j.url)}" target="_blank" rel="noopener">Open ↗</a></div></div>`).join('') || '<p class="mu">No gaps found — uncheck the filter.</p>'}
  <p class="sm mu">${R.dataset.count} real US postings · ${esc((R.dataset.scrapedAt || '').slice(0, 10))}</p>
  <div class="sticky"><span>${SEL.size} / 3 selected</span><button class="btn" id="toRoadmap" ${SEL.size ? '' : 'disabled'}>Build my roadmap →</button></div>`;
  $('#onlyGaps').onchange = e => { ONLY_GAPS = e.target.checked; keepScroll(renderReport); };
  $$('[data-j]').forEach(c => c.onchange = () => {
    if (c.checked && SEL.size >= 3) { c.checked = false; toast('Up to 3 vacancies'); return; }
    c.checked ? SEL.add(c.dataset.j) : SEL.delete(c.dataset.j); keepScroll(renderReport);
  });
  $('#toRoadmap').onclick = makeRoadmap;
}
function keepScroll(fn) { const y = scrollY; fn(); scrollTo(0, y); }
async function makeRoadmap() {
  location.hash = '#/app/roadmap'; $('#v-roadmap').innerHTML = `<div class="card">${spin('Building your 90-day roadmap')}</div>`;
  try { ME.roadmap = await api('/api/roadmap', { jobIds: [...SEL] }); ME.interview = ME.result = null; track('roadmap_generated'); $('#v-roadmap').innerHTML = ''; route(); }
  catch (x) { $('#v-roadmap').innerHTML = `<div class="card"><div class="err">${esc(x.message)}</div><div class="row"><button class="btn blue" onclick="makeRoadmap()">Retry</button><a class="btn ghost" href="#/app/report">Back</a></div></div>`; }
}

// ---------- roadmap ----------
function renderRoadmap() {
  const R = ME.roadmap, v = $('#v-roadmap');
  if (v.querySelector('.loading')) return;
  if (!R) { v.innerHTML = empty('Pick up to 3 vacancies in your report first.', 'report', 'Go to report →'); return; }
  v.innerHTML = `<div class="blk blue" style="margin-top:10px"><div class="lbl">90-day roadmap</div><div class="big">${esc(R.targetRole)}</div>
    <div class="sub">${esc(R.summary)}</div>
    <details style="margin-top:10px"><summary>Built for ${R.vacancies.length} vacanc${R.vacancies.length > 1 ? 'ies' : 'y'}</summary>${R.vacancies.map(j => `<div class="sm"><a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)} · ${esc(j.company)}</a></div>`).join('')}</details></div>
  ${R.milestones.map((m, i) => `<div class="ms"><div class="head"><div class="step" style="padding:0;grid-template-columns:40px"><div class="n" style="background:${['var(--blue)', 'var(--yellow)', 'var(--green)'][i]};color:${i === 1 ? 'var(--onyellow)' : '#fff'}">${i + 1}</div></div>
      <div><b>${esc(m.period)}</b><div>${m.skills.map(s => `<span class="chip">${esc(s)}</span>`).join('')}</div></div>${m.hours ? `<span class="sm mu" style="margin-left:auto">~${m.hours} h/week</span>` : ''}</div>
    <div><b class="sm">Deliverable:</b> ${esc(m.deliverable)}</div>
    <details style="margin-top:8px"><summary>Objectives & assignments</summary><ul class="sm">${[...m.objectives, ...m.assignments].map(o => `<li>${esc(o)}</li>`).join('')}</ul><div class="sm"><b>Done when:</b> ${esc(m.outcome)}</div></details>
    <div class="links" style="margin-top:12px">${m.resources.map(r => `<a href="${esc(r.url)}" target="_blank" rel="noopener" data-learn>${esc(r.title)} ↗</a>`).join('')}</div></div>`).join('')}
  <div class="row" style="justify-content:flex-end"><a class="btn blue big" href="#/app/interview">Check yourself →</a></div>`;
  $$('[data-learn]').forEach(a => a.onclick = () => track('learning_action_clicked'));
}

// ---------- interview ----------
function renderInterview() {
  const v = $('#v-interview'), I = ME.interview, Res = ME.result;
  if (v.querySelector('.loading')) return;
  if (!ME.roadmap) { v.innerHTML = empty('The interview checks your roadmap skills.', 'roadmap', 'Go to roadmap →'); return; }
  if (!I) {
    v.innerHTML = `<div class="blk yellow" style="max-width:760px;margin:10px auto"><div class="lbl">AI interview</div><div class="big">5 quick + 2 open</div>
      <div class="sub">On your ${esc(ME.roadmap.targetRole)} roadmap skills. Learning feedback, not a hiring decision.</div><div id="iErr"></div>
      <button class="btn" id="startI" style="margin-top:16px">Start</button></div>`;
    $('#startI').onclick = async () => {
      v.innerHTML = `<div class="card">${spin('Preparing questions')}</div>`;
      try { ME.interview = await api('/api/interview/questions', {}); PICKS = {}; track('interview_started'); v.innerHTML = ''; renderInterview(); }
      catch (x) { v.innerHTML = ''; renderInterview(); $('#iErr').innerHTML = `<div class="err">${esc(x.message)}</div>`; }
    };
    return;
  }
  const mres = Res ? Object.fromEntries(Res.mcq.map(m => [m.id, m])) : {};
  v.innerHTML = `<div style="max-width:860px;margin:10px auto 0">
    ${Res ? `<div class="grid2"><div class="blk green"><div class="lbl">Quiz</div><div class="big">${Res.mcqScore}/${Res.mcqTotal}</div></div>
      <div class="blk blue"><div class="lbl">Open answers</div><div class="big">${Res.open.map(o => o.totalScore + '%').join(' · ')}</div></div></div>` : ''}
    ${I.mcq.map((q, n) => { const r = mres[q.id]; return `<div class="mcq"><div class="sm mu">${n + 1} · ${esc(q.skill)}</div><b>${esc(q.question)}</b>
      ${q.options.map((o, i) => `<label class="${r ? (i === r.answer ? 'right' : i === r.picked ? 'wrong' : '') : ''}"><input type="radio" name="${q.id}" value="${i}" ${(r ? r.picked : PICKS[q.id]) === i ? 'checked' : ''} ${r ? 'disabled' : ''}>${esc(o)}</label>`).join('')}
      ${r && r.explanation ? `<details><summary>Why</summary><div class="sm">${esc(r.explanation)}</div></details>` : ''}</div>`; }).join('')}
    ${I.open.map((q, n) => { const e = Res && Res.open.find(o => o.id === q.id); return `<div class="card"><div class="sm mu">Open ${n + 1} · ${esc(q.skill)}</div><b>${esc(q.question)}</b>
      <textarea data-o="${q.id}" style="margin-top:10px;min-height:120px" placeholder="4–8 sentences with a concrete example" ${Res ? 'disabled' : ''}>${esc((ME._answers || {})[q.id] || (ME._draft || {})[q.id] || '')}</textarea>
      ${e ? evalHtml(e) : ''}</div>`; }).join('')}
    <div id="iErr"></div>
    <div class="row" style="justify-content:flex-end">${Res ? '<a class="btn blue big" href="#/app/feedback">Continue →</a>' : '<button class="btn blue big" id="finish">Finish</button>'}</div></div>`;
  $$('.mcq input').forEach(r => r.onchange = () => PICKS[r.name] = +r.value);
  $$('[data-o]').forEach(t => t.oninput = () => (ME._draft = { ...(ME._draft || {}), [t.dataset.o]: t.value }));
  $('#finish') && ($('#finish').onclick = async () => {
    const open = $$('[data-o]').map(t => ({ id: t.dataset.o, answer: t.value.trim() }));
    if (I.mcq.some(q => PICKS[q.id] === undefined)) return ($('#iErr').innerHTML = '<div class="err">Answer all quiz questions.</div>');
    if (open.some(o => !o.answer)) return ($('#iErr').innerHTML = '<div class="err">Answer the open questions.</div>');
    const b = $('#finish'); b.disabled = true; b.innerHTML = '<span class="spin"></span> Scoring';
    try { ME.result = await api('/api/interview/submit', { mcq: PICKS, open }); ME._answers = Object.fromEntries(open.map(o => [o.id, o.answer])); track('interview_completed'); route(); }
    catch (x) { $('#iErr').innerHTML = `<div class="err">${esc(x.message)} Your answers are kept.</div>`; b.disabled = false; b.textContent = 'Finish'; }
  });
}
function evalHtml(e) {
  return `<div style="margin-top:14px"><div class="row"><div class="score">${e.totalScore}%</div><span class="sm mu">rubric score</span></div>
  ${e.shortAnswer ? '<div class="err">Too short to score higher.</div>' : ''}
  <details style="margin-top:8px"><summary>Breakdown</summary>
  ${e.rubricScores.map(r => `<div class="rub"><span class="sm">${esc(r.criterion)}</span><div class="bar"><i style="width:${r.score * 25}%"></i></div><b>${r.score}/4</b></div>`).join('')}
  <div class="sm">${e.strengths.map(s => `<span class="chip g">${esc(s)}</span>`).join('')}${e.weaknesses.map(s => `<span class="chip y">${esc(s)}</span>`).join('')}</div>
  ${e.improvedStructure ? `<div class="sm mu" style="white-space:pre-line;margin-top:6px">${esc(e.improvedStructure)}</div>` : ''}</details></div>`;
}

// ---------- feedback ----------
const FB = { rating: 0, pro: '' };
function renderFeedback() {
  const v = $('#v-feedback');
  if (ME.feedbackDone) { v.innerHTML = `<div class="blk green" style="max-width:600px;margin:20px auto;text-align:center"><div class="big">Thank you!</div><a class="btn" style="margin-top:12px" href="#/app/report">Back to report</a></div>`; return; }
  v.innerHTML = `<div class="card" style="max-width:600px;margin:20px auto">
    <h2>Was it useful?</h2><div class="stars" id="fbStars"></div>
    <h2 style="margin-top:20px">Would you buy Pro?</h2><p class="sm mu" style="margin:0 0 10px">$15–19/month · vacancy alerts, progress tracking, repeat interviews. Nothing is charged.</p>
    <div class="choice">${['Yes', 'Maybe', 'No'].map(x => `<button class="btn ghost small ${FB.pro === x ? 'on' : ''}" data-p="${x}">${x}</button>`).join('')}</div>
    <textarea id="fbCom" style="min-height:90px;margin-top:18px" placeholder="Anything else? (optional)"></textarea>
    <div id="fErr"></div><div class="row" style="margin-top:14px;justify-content:flex-end"><button class="btn blue" id="fbSend">Send</button></div></div>`;
  const stars = () => { $('#fbStars').innerHTML = [1, 2, 3, 4, 5].map(i => `<button class="${i <= FB.rating ? 'on' : ''}" data-r="${i}" aria-label="${i} stars">★</button>`).join(''); $$('[data-r]').forEach(b => b.onclick = () => { FB.rating = +b.dataset.r; stars(); }); };
  stars();
  $$('[data-p]').forEach(b => b.onclick = () => { FB.pro = b.dataset.p; $$('[data-p]').forEach(x => x.classList.toggle('on', x === b)); });
  $('#fbSend').onclick = async () => {
    if (!FB.rating) return ($('#fErr').innerHTML = '<div class="err">Please rate first.</div>');
    try { await api('/api/feedback', { helpfulRating: FB.rating, buyPro: FB.pro, comment: $('#fbCom').value }); ME.feedbackDone = true; route(); }
    catch (x) { $('#fErr').innerHTML = `<div class="err">${esc(x.message)}</div>`; }
  };
}

// ---------- theme ----------
const curTheme = () => document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
function themeBtn() { const d = curTheme() === 'dark'; $('#theme').textContent = d ? '☀' : '☾'; $('#theme').title = d ? 'Light mode' : 'Dark mode'; }
$('#theme').onclick = () => {
  const next = curTheme() === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = next;
  try { localStorage.setItem('tirek-theme', next); } catch (e) {}
  themeBtn();
};
matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', themeBtn);
themeBtn();

// ---------- ambient music (generated in the browser) ----------
let AC, mg, lp, loop, play = 0, ci = 0;
const CH = [[130.8, 261.6, 329.6, 392, 493.9], [110, 220, 261.6, 329.6, 392], [87.3, 174.6, 220, 261.6, 329.6], [98, 196, 246.9, 293.7, 392]], PE = [523.3, 587.3, 659.3, 784, 880, 1046.5];
function tone(f, t, d, g, ty) { const o = AC.createOscillator(), e = AC.createGain(); o.type = ty; o.frequency.value = f; e.gain.setValueAtTime(0, t); e.gain.linearRampToValueAtTime(g, t + d * .35); e.gain.exponentialRampToValueAtTime(.0001, t + d); o.connect(e); e.connect(lp); o.start(t); o.stop(t + d + .1); }
function bar() { const t = AC.currentTime + .05; CH[ci % 4].forEach(f => tone(f, t, 9, .045, 'sine')); for (let k = 0; k < 5; k++) tone(PE[Math.floor(Math.random() * PE.length)], t + k * 1.6 + .4, 3.2, .035, 'triangle'); ci++; loop = setTimeout(bar, 8000); }
function music() {
  play = !play; const b = $('#mus'); b.classList.toggle('on', play); b.setAttribute('aria-pressed', play); $('#mt').textContent = play ? 'Playing' : 'Music'; $('#vol').classList.toggle('hide', !play);
  if (play) {
    if (!AC) { AC = new (window.AudioContext || window.webkitAudioContext)(); mg = AC.createGain(); mg.gain.value = 0; lp = AC.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 1500; const dl = AC.createDelay(), fb = AC.createGain(); dl.delayTime.value = .5; fb.gain.value = .38; lp.connect(mg); lp.connect(dl); dl.connect(fb); fb.connect(dl); dl.connect(mg); mg.connect(AC.destination); }
    AC.resume(); mg.gain.cancelScheduledValues(AC.currentTime); mg.gain.linearRampToValueAtTime($('#vol').value / 100, AC.currentTime + 2); bar();
  } else { clearTimeout(loop); mg.gain.linearRampToValueAtTime(0, AC.currentTime + 1.5); }
}
$('#mus').onclick = () => { try { music(); } catch (e) { toast('Sound is not available'); } };
$('#vol').oninput = e => { if (mg && play) mg.gain.value = e.target.value / 100; };

// ---------- boot ----------
(async function () {
  try { ROLES = (await api('/api/roles')).roles; } catch (e) { toast('Server is offline'); }
  try { ME = await api('/api/me'); } catch (e) { ME = null; }
  route();
})();
