// tirek — Career Insurance: landing → auth → profile → report → roadmap → interview → feedback
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = n => '$' + Math.round(n).toLocaleString('en-US');
let tt; function toast(t) { const e = $('#toast'); e.textContent = t; e.classList.add('on'); clearTimeout(tt); tt = setTimeout(() => e.classList.remove('on'), 2600); }
const spin = t => `<div class="loading"><span class="spin" style="width:28px;height:28px"></span><b>${esc(t)}</b><span class="sm" id="loadStep"></span></div>`;

async function api(path, body) {
  const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({ error: 'Server returned an invalid response.' }));
  if (r.status === 401 && path !== '/api/login' && path !== '/api/me') { ME = null; location.hash = '#/login'; }
  if (!r.ok) throw new Error(j.error || 'Request failed.');
  return j;
}
const track = name => api('/api/event', { name }).catch(() => {});

let ME = null, ROLES = [], CV = { text: '', name: '' }, SEL = new Set(), ONLY_GAPS = true, PICKS = {};
const TABS = [['profile', 'Profile'], ['report', 'Career report'], ['roadmap', 'Learning roadmap'], ['interview', 'AI interview'], ['feedback', 'Feedback']];
const PUBLIC = ['landing', 'login', 'signup'], VIEWS = [...PUBLIC, ...TABS.map(t => t[0])];
const SALARIES = ['Under $50k', '$50k–$75k', '$75k–$100k', '$100k–$130k', '$130k–$160k', '$160k–$200k', '$200k+'];
const HOURS = ['1–2 h / week', '3–5 h / week', '6–10 h / week', '10+ h / week'];

// ---------- routing ----------
function route() {
  const h = location.hash.replace(/^#\/?/, '');
  let view = h.startsWith('app/') ? h.slice(4) : (h || 'landing');
  if (!VIEWS.includes(view)) view = 'landing';
  if (!ME && !PUBLIC.includes(view)) { location.hash = '#/login'; return; }
  if (ME && PUBLIC.includes(view)) { location.hash = '#/app/' + (ME.report ? 'report' : 'profile'); return; }
  VIEWS.forEach(v => $('#v-' + v).classList.toggle('hide', v !== view));
  const app = !PUBLIC.includes(view);
  ['#nav', '#logout', '#who', '#mus'].forEach(s => $(s).classList.toggle('hide', !app));
  if (!app) $('#vol').classList.add('hide'); else $('#vol').classList.toggle('hide', !play);
  if (app) {
    $('#who').textContent = ME.user.name + ' ' + ME.user.surname;
    $('#nav').innerHTML = TABS.map(([k, n]) => `<button class="${k === view ? 'on' : ''}" data-t="${k}">${n}${done(k) ? '<i>✓</i>' : ''}</button>`).join('');
    $$('#nav button').forEach(b => b.onclick = () => location.hash = '#/app/' + b.dataset.t);
  }
  if (view === 'landing') window.TirekMap && TirekMap.resize();
  ({ profile: renderProfile, report: renderReport, roadmap: renderRoadmap, interview: renderInterview, feedback: renderFeedback })[view]?.();
  scrollTo(0, 0);
}
const done = k => ({ profile: !!ME.report, report: !!ME.roadmap, roadmap: !!ME.roadmap, interview: !!ME.result, feedback: ME.feedbackDone })[k];
addEventListener('hashchange', route);

// ---------- auth ----------
function formJSON(f) { return Object.fromEntries(new FormData(f).entries()); }
async function authSubmit(e, path) {
  e.preventDefault(); const f = e.target, b = f.querySelector('button[type=submit]'), err = f.querySelector('.ferr');
  err.textContent = ''; b.disabled = true;
  try { await api(path, formJSON(f)); ME = await api('/api/me'); f.reset(); location.hash = '#/app/profile'; toast('Welcome, ' + ME.user.name + '!'); }
  catch (x) { err.textContent = x.message; }
  b.disabled = false;
}
$('#loginForm').onsubmit = e => authSubmit(e, '/api/login');
$('#signupForm').onsubmit = e => authSubmit(e, '/api/signup');
$('#logout').onclick = async () => { await api('/api/logout', {}).catch(() => {}); ME = null; CV = { text: '', name: '' }; SEL.clear(); location.hash = '#/'; toast('You are logged out'); };

// ---------- profile ----------
const SAMPLE = `Maya R. — Data Analyst, New York, NY. 4 years of experience.
Data Analyst at a retail marketplace (2022–present): SQL queries in PostgreSQL on orders and customer behavior; Tableau dashboards for merchandising; automated monthly reporting with Python (pandas), saving 6 hours per month; presented findings to stakeholders in leadership reviews.
Junior Analyst at a logistics company (2020–2022): advanced Excel modeling with pivot tables, tracked funnel and retention metrics.
Education: BA Economics, CUNY. Preferred: hybrid in New York, $110k+.`;
function renderProfile() {
  const inp = ME.input || {};
  const opt = (arr, v) => arr.map(x => `<option ${x === v ? 'selected' : ''}>${esc(x)}</option>`).join('');
  $('#v-profile').innerHTML = `
  <div class="grid2">
    <div class="card"><h2>Your CV</h2><p class="mu sm">PDF (text, up to 5 MB) or .txt. The file is read in your browser; the CV is not stored on our server.</p>
      <label class="drop ${CV.text ? 'ok' : ''}" id="drop" style="display:block;cursor:pointer">${CV.text ? `✓ ${esc(CV.name)} · ${CV.text.length.toLocaleString()} characters read<br><span class="sm mu">Click to replace</span>` : '<b>Upload CV</b><br><span class="sm">Click to choose a file</span>'}
        <input type="file" id="cvFile" accept="application/pdf,.txt,text/plain" hidden></label>
      <div class="row" style="margin-top:10px"><button class="btn soft small" id="sample">Use a sample CV</button>${CV.text ? '<button class="btn soft small" id="clearCv">Remove CV</button>' : ''}</div>
      <div id="cvErr"></div>
    </div>
    <div class="card"><h2>About yourself</h2>
      <textarea id="about" style="min-height:190px" placeholder="Work experience, education, skills, preferred workplace, preferred salary, preferred location, work type (Remote / Hybrid / Office)…">${esc(inp.about || '')}</textarea>
    </div>
  </div>
  <div class="card"><h2>Your goal</h2>
    <div class="grid2" style="grid-template-columns:repeat(4,1fr);gap:12px">
      <label class="fld">Current role<select id="curRole">${opt([...ROLES, 'Other'], inp.currentRole || 'Data Analyst')}</select></label>
      <label class="fld">Target role<select id="tgtRole">${opt(ROLES, inp.targetRole || 'Data Scientist')}</select></label>
      <label class="fld">Target salary (per year)<select id="tgtSal">${opt(SALARIES, inp.targetSalary || '$100k–$130k')}</select></label>
      <label class="fld">Study time<select id="hours">${opt(HOURS, inp.studyHours || '3–5 h / week')}</select></label>
    </div>
    <div id="pErr"></div>
    <div class="row" style="margin-top:16px;justify-content:flex-end"><button class="btn ac big" id="gen">Generate career report →</button></div>
  </div>`;
  $('#cvFile').onchange = readCv;
  $('#sample').onclick = () => { CV = { text: SAMPLE, name: 'sample-cv.txt' }; keepAbout(); renderProfile(); };
  $('#clearCv') && ($('#clearCv').onclick = () => { CV = { text: '', name: '' }; keepAbout(); renderProfile(); });
  $('#gen').onclick = generate;
}
function keepAbout() { ME.input = { ...(ME.input || {}), about: $('#about').value, currentRole: $('#curRole').value, targetRole: $('#tgtRole').value, targetSalary: $('#tgtSal').value, studyHours: $('#hours').value }; }
async function readCv(e) {
  const f = e.target.files[0]; if (!f) return; keepAbout();
  const fail = m => { $('#cvErr').innerHTML = `<div class="err">${esc(m)}</div>`; };
  if (f.size > 5e6) return fail('File is larger than 5 MB. Paste the text into “About yourself” instead.');
  try {
    let text = '';
    if (f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')) {
      if (!window.pdfjsLib) return fail('PDF reader unavailable. Paste your CV text into “About yourself”.');
      pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      const pdf = await pdfjsLib.getDocument({ data: await f.arrayBuffer() }).promise;
      for (let i = 1; i <= Math.min(pdf.numPages, 8); i++) text += (await (await pdf.getPage(i)).getTextContent()).items.map(x => x.str).join(' ') + '\n';
    } else text = await f.text();
    if (text.trim().length < 50) return fail('No text found in this file (scanned PDF?). Paste your CV into “About yourself”.');
    CV = { text: text.trim(), name: f.name }; renderProfile();
  } catch (x) { fail('Could not read this file. Paste your CV into “About yourself”.'); }
}
async function generate() {
  keepAbout(); const i = ME.input;
  if ((CV.text + i.about).trim().length < 40) { $('#pErr').innerHTML = '<div class="err">Upload your CV or write a few sentences about yourself.</div>'; return; }
  track('report_started');
  $('#v-profile').innerHTML = `<div class="card">${spin('Building your career report…')}</div>`;
  const steps = ['Reading your CV and profile…', 'Comparing your skills with real US vacancies…', 'Calculating your Career Risk Score…', 'Finding alternative roles…'];
  let k = 0; const iv = setInterval(() => { const e = $('#loadStep'); if (e) e.textContent = steps[Math.min(k++, steps.length - 1)]; }, 2500); $('#loadStep').textContent = steps[k++];
  try {
    ME.report = await api('/api/report', { cvText: CV.text, about: i.about, currentRole: i.currentRole, targetRole: i.targetRole, targetSalary: i.targetSalary, studyHours: i.studyHours });
    ME.roadmap = ME.interview = ME.result = null; SEL.clear(); clearInterval(iv); location.hash = '#/app/report';
    if (location.hash === '#/app/report') route();
  } catch (x) { clearInterval(iv); renderProfile(); $('#pErr').innerHTML = `<div class="err">${esc(x.message)}</div>`; }
}

// ---------- report ----------
function empty(msg, to, label) { return `<div class="card empty">${esc(msg)}<br><br><a class="btn" href="#/app/${to}">${esc(label)}</a></div>`; }
const salTxt = s => !s ? 'Not stated in postings' : `${money(s.median)} median/yr <span class="mu sm">(${s.n} posting${s.n > 1 ? 's' : ''} with pay, ${money(s.min)}–${money(s.max)})</span>`;
const jobSal = s => !s ? '' : (s.text ? esc(s.text) : `${money(s.min)}${s.max ? '–' + money(s.max) : ''}${s.period === 'hour' ? '/h' : '/yr'}`);
function renderReport() {
  const R = ME.report, v = $('#v-report');
  if (!R) { v.innerHTML = empty('No report yet. Fill in your profile first.', 'profile', 'Go to profile →'); return; }
  const rk = R.risk, lvl = rk.level.split(' ')[0].toLowerCase();
  const trend = (cls, icon, title, sub, items, lab, labCls) => `<div class="trend"><div class="ico ${cls}">${icon}</div><div><b style="font-size:17px">${title}</b><div class="sm mu">${sub}</div>
    <div style="margin-top:4px">${items.length ? items.map(x => `<span title="${esc(x.reason)}">${esc(x.skill)}</span>`).join(', ') : '<span class="mu">—</span>'}</div>
    ${items.length ? `<div class="sm mu" style="margin-top:4px">${items.map(x => esc(x.reason)).filter(Boolean).slice(0, 2).join(' · ')}</div>` : ''}</div><span class="lab pill ${labCls}">${lab}</span></div>`;
  const vac = R.vacancies.filter(j => !ONLY_GAPS || j.missing.length);
  v.innerHTML = `
  <div class="grid2">
    <div class="card"><div class="riskhead"><h2 style="font-size:24px">Career Risk Score</h2><span class="pill ${lvl}">${esc(rk.level)}</span></div>
      <div class="bigscore" style="margin-top:10px">${rk.score}/100<small>${esc(rk.formula)}</small></div>
      <div class="rbar"><i style="width:${rk.score}%"></i></div>
      <h3 style="font-size:17px">What affects the risk:</h3>
      ${rk.factors.map(f => `<div class="factor"><b class="w">${Math.round(f.weight * 100)}%</b><div><b>${esc(f.name)}</b> <span class="mu sm">· value ${f.value} → ${f.contribution} pts</span><div class="sm mu">${esc(f.explanation)}</div></div></div>`).join('')}
      <p class="sm mu" style="margin:10px 0 0">Calculated on the server by a fixed formula, not by AI. Weights are demonstrational; in a real product they must be justified and calibrated on data. ${esc(R.dataset.estimatesNote)}</p>
    </div>
    <div class="card"><h2>Skills recommendations</h2>
      <div class="sm mu">Your detected skills: ${R.skills.map(s => `<span class="tag">${esc(s)}</span>`).join('') || '—'}</div>
      ${trend('up', '↗', 'Growing skills', 'Skills with rising demand — worth adding', R.growing, 'Growth', 'low')}
      ${trend('flat', '—', 'Stable skills', 'Skills with steady demand', R.stable, 'Stable', 'medium')}
      ${trend('down', '↘', 'Declining skills', 'Skills with potentially declining demand', R.declining, 'Risk', 'high')}
    </div>
  </div>
  <div class="grid2">
    <div class="card"><h2>Alternative directions</h2><p class="sm mu">Skill match = share of the most-requested skills for that role (in ${R.dataset.count} real US postings) that you already have. Click a role for details.</p>
      <table class="alt"><tr><th>Direction</th><th class="r">Skills match</th></tr>
      ${R.alternatives.map(a => `<tr><td colspan="2"><details class="altd"><summary><div class="row" style="justify-content:space-between"><b>${esc(a.role)}</b><b>${a.match}%</b></div></summary>
        <div class="sm" style="margin-top:10px;display:grid;gap:6px">
          ${a.why ? `<div class="mu">${esc(a.why)}</div>` : ''}
          <div><b>Skills that already fit:</b> ${[...new Set([...a.haveSkills, ...a.transferable])].map(s => `<span class="tag have">✓ ${esc(s)}</span>`).join('') || '—'}</div>
          <div><b>Missing skills:</b> ${[...new Set([...a.missingSkills, ...a.aiMissing])].slice(0, 8).map(s => `<span class="tag miss">${esc(s)}</span>`).join('') || '—'}</div>
          <div><b>Time to transition:</b> ${esc(a.time)} · difficulty ${esc(a.difficulty)} <span class="mu">(estimate)</span></div>
          <div><b>Salaries:</b> ${salTxt(a.salary)}</div>
          <div><b>Vacancies in dataset:</b> ${a.vacancies}</div>
          <div class="links"><b>Courses to start:</b> ${a.courses.map(c => `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title)} ↗</a>`).join('') || '—'}</div>
        </div></details></td></tr>`).join('')}</table>
    </div>
    <div class="card"><div class="riskhead"><h2>Your 90-day protection plan</h2><span class="pill low">Personalized</span></div>
      ${R.protectionPlan.map((p, i) => `<div class="plan"><div class="n">${i + 1}</div><div><b>${esc(p.period)}: ${esc(p.focus)}</b><div>${esc(p.actions)}</div><small>Result: ${esc(p.result)}</small></div></div>`).join('') || '<p class="mu">—</p>'}
    </div>
  </div>
  <div class="card"><div class="riskhead"><div><h2>Vacancies for you</h2><p class="sm mu" style="margin:0">Real US postings (${esc(R.dataset.note || '')} Scraped ${esc((R.dataset.scrapedAt || '').slice(0, 10))}). Pick up to 3 to build your learning roadmap.</p></div>
      <label class="row sm"><input type="checkbox" id="onlyGaps" ${ONLY_GAPS ? 'checked' : ''}> Only where I lack skills</label></div>
    ${vac.map(j => `<div class="vac ${SEL.has(j.id) ? 'sel' : ''}"><input type="checkbox" data-j="${esc(j.id)}" ${SEL.has(j.id) ? 'checked' : ''} aria-label="Select ${esc(j.title)}">
      <div><b>${esc(j.title)}</b> <span class="mu">· ${esc(j.company)}</span>
        <div class="sm mu">${esc(j.location)}${j.remote ? ' · remote' : ''} · ${esc(j.role)} · ${esc(j.level)}${j.salary ? ' · <b style="color:var(--tx)">' + jobSal(j.salary) + '</b>' : ' · salary not stated'}</div>
        <div style="margin-top:6px">${j.matched.map(s => `<span class="tag have">✓ ${esc(s)}</span>`).join('')}${j.missing.map(s => `<span class="tag miss">✗ ${esc(s)}</span>`).join('')}</div></div>
      <div style="text-align:right"><b>${j.fit}%</b><div class="sm mu">skill fit</div><a class="sm" href="${esc(j.url)}" target="_blank" rel="noopener">Open posting ↗</a></div></div>`).join('') || '<p class="mu">No vacancies with skill gaps — uncheck the filter to see all.</p>'}
  </div>
  <div class="sticky"><span>Selected <b>${SEL.size}</b> / 3 vacancies</span><button class="btn ac" id="toRoadmap" ${SEL.size ? '' : 'disabled'}>Generate learning roadmap →</button></div>`;
  $('#onlyGaps').onchange = e => { ONLY_GAPS = e.target.checked; renderReport(); };
  $$('[data-j]').forEach(c => c.onchange = () => {
    const id = c.dataset.j;
    if (c.checked && SEL.size >= 3) { c.checked = false; toast('You can choose up to 3 vacancies'); return; }
    c.checked ? SEL.add(id) : SEL.delete(id); const y = scrollY; renderReport(); scrollTo(0, y);
  });
  $('#toRoadmap').onclick = makeRoadmap;
}
async function makeRoadmap() {
  location.hash = '#/app/roadmap'; $('#v-roadmap').innerHTML = `<div class="card">${spin('Generating your 90-day learning roadmap…')}</div>`;
  try { ME.roadmap = await api('/api/roadmap', { jobIds: [...SEL] }); ME.interview = ME.result = null; track('roadmap_generated'); $('#v-roadmap').innerHTML = ''; route(); }
  catch (x) { $('#v-roadmap').innerHTML = `<div class="card"><div class="err">${esc(x.message)}</div><div class="row"><button class="btn" onclick="makeRoadmap()">Retry</button><a class="btn soft" href="#/app/report">Back to report</a></div></div>`; }
}

// ---------- roadmap ----------
function renderRoadmap() {
  const R = ME.roadmap, v = $('#v-roadmap');
  if (v.querySelector('.loading')) return;
  if (!R) { v.innerHTML = empty('Choose up to 3 vacancies in your career report to build a roadmap.', 'report', 'Go to career report →'); return; }
  v.innerHTML = `<div class="card"><div class="riskhead"><div><h2 style="font-size:24px">Your 90-day roadmap: ${esc(R.targetRole)}</h2><p class="mu" style="margin:4px 0 0">${esc(R.summary)}</p></div><span class="pill low">${R.durationDays} days</span></div>
    <p class="sm" style="margin:12px 0 0"><b>Built for:</b> ${R.vacancies.map(j => `<a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)} · ${esc(j.company)}</a>`).join(' &nbsp;·&nbsp; ')}</p>
    <p class="sm" style="margin:6px 0 0"><b>Skills to close:</b> ${R.missingSkills.map(s => `<span class="tag miss">${esc(s)}</span>`).join('') || '—'}</p></div>
  ${R.milestones.map((m, i) => `<div class="ms"><h3><span>${i + 1}. ${esc(m.period)}: ${m.skills.map(esc).join(', ')}</span>${m.hours ? `<span class="mu sm">~${m.hours} h/week</span>` : ''}</h3>
    <div class="grid2"><div><b class="sm">Learning objectives</b><ul class="sm">${m.objectives.map(o => `<li>${esc(o)}</li>`).join('')}</ul></div>
      <div><b class="sm">Practical assignments</b><ul class="sm">${m.assignments.map(o => `<li>${esc(o)}</li>`).join('')}</ul></div></div>
    <div class="sm"><b>Deliverable:</b> ${esc(m.deliverable)}</div><div class="sm"><b>Measurable outcome:</b> ${esc(m.outcome)}</div>
    <div class="links" style="margin-top:10px"><b class="sm">Learning materials:</b><br>${m.resources.map(r => `<a href="${esc(r.url)}" target="_blank" rel="noopener" data-learn>${esc(r.title)} ↗</a>`).join('')}</div></div>`).join('')}
  <div class="row" style="justify-content:flex-end"><a class="btn ac big" href="#/app/interview">Check yourself: AI interview →</a></div>`;
  $$('[data-learn]').forEach(a => a.onclick = () => track('learning_action_clicked'));
}

// ---------- interview ----------
function renderInterview() {
  const v = $('#v-interview'), I = ME.interview, Res = ME.result;
  if (v.querySelector('.loading')) return;
  if (!ME.roadmap) { v.innerHTML = empty('The interview checks skills from your learning roadmap.', 'roadmap', 'Go to roadmap →'); return; }
  if (!I) {
    v.innerHTML = `<div class="card" style="max-width:760px;margin:0 auto"><h2>AI interview: ${esc(ME.roadmap.targetRole)}</h2>
      <p class="mu">5 multiple-choice questions and 2 open questions on the skills from your roadmap. Open answers are scored on a fixed rubric (technical correctness, reasoning, evidence, clarity). Learning feedback — not a hiring decision.</p>
      <div id="iErr"></div><button class="btn ac" id="startI">Start interview</button></div>`;
    $('#startI').onclick = async () => {
      v.innerHTML = `<div class="card">${spin('Preparing your questions…')}</div>`;
      try { ME.interview = await api('/api/interview/questions', {}); PICKS = {}; track('interview_started'); v.innerHTML = ''; renderInterview(); }
      catch (x) { v.innerHTML = ''; renderInterview(); $('#iErr').innerHTML = `<div class="err">${esc(x.message)}</div>`; }
    };
    return;
  }
  const mres = Res ? Object.fromEntries(Res.mcq.map(m => [m.id, m])) : {};
  v.innerHTML = `<div style="max-width:860px;margin:0 auto">
    ${Res ? `<div class="card"><div class="riskhead"><h2>Your results</h2><span class="pill low">Quiz ${Res.mcqScore}/${Res.mcqTotal}</span></div>
      <p class="mu sm" style="margin:0">Open answers: ${Res.open.map(o => o.totalScore + '%').join(' · ')} on the rubric. Review the explanations below.</p></div>` : ''}
    <h3 style="margin:6px 4px 10px">Multiple choice</h3>
    ${I.mcq.map((q, n) => { const r = mres[q.id]; return `<div class="mcq"><div class="sm mu">${n + 1} · ${esc(q.skill)}</div><b>${esc(q.question)}</b>
      ${q.options.map((o, i) => `<label class="${r ? (i === r.answer ? 'right' : i === r.picked ? 'wrong' : '') : ''}"><input type="radio" name="${q.id}" value="${i}" ${(r ? r.picked : PICKS[q.id]) === i ? 'checked' : ''} ${r ? 'disabled' : ''}>${esc(o)}</label>`).join('')}
      ${r ? `<div class="sm" style="margin-top:6px">${r.correct ? '✅ Correct.' : '❌ Not quite.'} ${esc(r.explanation)}</div>` : ''}</div>`; }).join('')}
    <h3 style="margin:16px 4px 10px">Open questions</h3>
    ${I.open.map((q, n) => { const e = Res && Res.open.find(o => o.id === q.id); return `<div class="card"><div class="sm mu">${n + 1} · ${esc(q.skill)}</div><b>${esc(q.question)}</b>
      <textarea data-o="${q.id}" style="margin-top:10px;min-height:120px" placeholder="Answer in 4–8 sentences with a concrete example…" ${Res ? 'disabled' : ''}>${esc((Res && ME._answers?.[q.id]) || ME._draft?.[q.id] || '')}</textarea>
      ${e ? evalHtml(e) : ''}</div>`; }).join('')}
    <div id="iErr"></div>
    <div class="row" style="justify-content:flex-end">${Res ? '<a class="btn ac big" href="#/app/feedback">Continue →</a>' : '<button class="btn ac big" id="finish">Finish interview</button>'}</div></div>`;
  $$('.mcq input').forEach(r => r.onchange = () => PICKS[r.name] = +r.value);
  $$('[data-o]').forEach(t => t.oninput = () => (ME._draft = { ...(ME._draft || {}), [t.dataset.o]: t.value }));
  $('#finish') && ($('#finish').onclick = async () => {
    const open = $$('[data-o]').map(t => ({ id: t.dataset.o, answer: t.value.trim() }));
    if (I.mcq.some(q => PICKS[q.id] === undefined)) return ($('#iErr').innerHTML = '<div class="err">Please answer all multiple-choice questions.</div>');
    if (open.some(o => !o.answer)) return ($('#iErr').innerHTML = '<div class="err">Please answer the open questions.</div>');
    const b = $('#finish'); b.disabled = true; b.innerHTML = '<span class="spin"></span>Evaluating…';
    try { ME.result = await api('/api/interview/submit', { mcq: PICKS, open }); ME._answers = Object.fromEntries(open.map(o => [o.id, o.answer])); route(); scrollTo(0, 0); }
    catch (x) { $('#iErr').innerHTML = `<div class="err">${esc(x.message)} Your answers are kept — press Finish to retry.</div>`; b.disabled = false; b.textContent = 'Finish interview'; }
  });
}
function evalHtml(e) {
  return `<div style="margin-top:12px;border-top:1px solid var(--ln);padding-top:12px"><div class="row"><div class="score">${e.totalScore}%</div><span class="sm mu">Rubric score · sum of 4 criteria / 16</span></div>
  ${e.shortAnswer ? '<div class="notice">Very short answer: not enough evidence to score higher.</div>' : ''}
  ${e.rubricScores.map(r => `<div class="rub"><b class="sm">${esc(r.criterion)}</b><div><div class="bar"><i style="width:${r.score * 25}%"></i></div><span class="sm mu">${esc(r.explanation)}</span></div><b>${r.score}/4</b></div>`).join('')}
  <div class="grid2 sm"><div><b>Strengths</b><ul>${e.strengths.map(s => `<li>${esc(s)}</li>`).join('') || '<li>—</li>'}</ul></div><div><b>Missing points</b><ul>${e.weaknesses.map(s => `<li>${esc(s)}</li>`).join('') || '<li>—</li>'}</ul></div></div>
  ${e.cited.length ? e.cited.map(c => `<blockquote>“${esc(c)}”</blockquote>`).join('') : ''}
  ${e.improvedStructure ? `<div class="sm"><b>A stronger structure:</b><div class="mu" style="white-space:pre-line">${esc(e.improvedStructure)}</div></div>` : ''}</div>`;
}

// ---------- feedback ----------
const FB = { rating: 0, pro: '' };
function renderFeedback() {
  const v = $('#v-feedback');
  if (ME.feedbackDone) { v.innerHTML = `<div class="card empty" style="max-width:600px;margin:20px auto"><h2>Thank you!</h2>Your feedback helps us build tirek.<br><br><a class="btn soft" href="#/app/report">Back to my report</a></div>`; return; }
  v.innerHTML = `<div class="card" style="max-width:640px;margin:20px auto">
    <h2>Was it useful?</h2><div class="stars" id="fbStars"></div>
    <h3 style="margin-top:18px">Would you buy the Pro version?</h3>
    <p class="sm mu" style="margin:0 0 8px">Pro ($15–19 / month, not live yet): monitoring of new vacancies for your target, more career goals, repeat interviews and progress tracking. No payment is taken.</p>
    <div class="choice" id="fbPro">${['Yes', 'Maybe', 'No'].map(x => `<button class="btn soft small ${FB.pro === x ? 'on' : ''}" data-p="${x}">${x}</button>`).join('')}</div>
    <h3 style="margin-top:18px">Anything else?</h3><textarea id="fbCom" style="min-height:100px" placeholder="What was most useful? What blocked you?"></textarea>
    <div id="fErr"></div><div class="row" style="margin-top:12px;justify-content:flex-end"><button class="btn ac" id="fbSend">Send feedback</button></div></div>`;
  const stars = () => { $('#fbStars').innerHTML = [1, 2, 3, 4, 5].map(i => `<button class="${i <= FB.rating ? 'on' : ''}" data-r="${i}" aria-label="${i} stars">★</button>`).join(''); $$('[data-r]').forEach(b => b.onclick = () => { FB.rating = +b.dataset.r; stars(); }); };
  stars();
  $$('[data-p]').forEach(b => b.onclick = () => { FB.pro = b.dataset.p; $$('[data-p]').forEach(x => x.classList.toggle('on', x === b)); });
  $('#fbSend').onclick = async () => {
    if (!FB.rating) return ($('#fErr').innerHTML = '<div class="err">Please rate how useful it was.</div>');
    try { await api('/api/feedback', { helpfulRating: FB.rating, buyPro: FB.pro, comment: $('#fbCom').value }); ME.feedbackDone = true; route(); }
    catch (x) { $('#fErr').innerHTML = `<div class="err">${esc(x.message)}</div>`; }
  };
}

// ---------- theme ----------
const curTheme = () => document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
function themeBtn() { const d = curTheme() === 'dark'; $('#theme').textContent = d ? '☀' : '☾'; $('#theme').title = d ? 'Switch to light mode' : 'Switch to dark mode'; }
$('#theme').onclick = () => {
  const next = curTheme() === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = next;
  try { localStorage.setItem('tirek-theme', next); } catch (e) {}
  themeBtn();
};
matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', themeBtn);
themeBtn();

// ---------- ambient music (generated in the browser, no files) ----------
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
$('#mus').onclick = () => { try { music(); } catch (e) { toast('Sound is not available in this browser'); } };
$('#vol').oninput = e => { if (mg && play) mg.gain.value = e.target.value / 100; };

// ---------- boot ----------
(async function () {
  try { ROLES = (await api('/api/roles')).roles; } catch (e) { toast('Server is offline'); }
  try { ME = await api('/api/me'); } catch (e) { ME = null; }
  route();
})();
