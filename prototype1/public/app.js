// Career Insurance prototype: profile → report → AI interview → growth plan → feedback
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = x => Math.round(x * 100) + '%';
let tt; function toast(t) { const e = $('#toast'); e.textContent = t; e.classList.add('on'); clearTimeout(tt); tt = setTimeout(() => e.classList.remove('on'), 2400); }

let sid = 'anon'; try { sid = sessionStorage.getItem('sid') || crypto.randomUUID(); sessionStorage.setItem('sid', sid); } catch (e) { sid = Math.random().toString(36).slice(2); }
const S = { tab: 'main', data: null, skills: [], method: '', report: null, sim: new Set(), gap: null, qs: null, qi: 0, evals: [], done: { report: 0, interview: 0 }, fb: { rating: 0 } };
const TABS = [['main', 'Main'], ['profile', '1 · Profile'], ['report', '2 · Career report'], ['interview', '3 · AI interview'], ['plan', '4 · Growth plan']];

async function api(path, body) {
  const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({ error: 'Server returned an invalid response.' }));
  if (!r.ok) throw new Error(j.error || 'Request failed.');
  return j;
}
const track = name => api('/api/event', { name, sid }).catch(() => {});

// ---------- navigation ----------
function nav() {
  $('#nav').innerHTML = TABS.map(([k, n]) => {
    const ok = (k === 'report' && S.report) || (k === 'interview' && S.done.interview) || (k === 'plan' && S.evals.length);
    return `<button class="${S.tab === k ? 'on' : ''}" data-t="${k}">${n}${ok ? '<i>✓</i>' : ''}</button>`;
  }).join('');
  $$('#nav button').forEach(b => b.onclick = () => go(b.dataset.t));
}
function go(t) {
  S.tab = t;
  TABS.forEach(([k]) => $('#v-' + k).classList.toggle('hide', k !== t));
  nav(); scrollTo({ top: 0, behavior: 'smooth' });
  if (t === 'main') window.TirekMap && TirekMap.resize();
  ({ report: renderReport, interview: renderInterview, plan: renderPlan })[t]?.();
}

// ---------- profile ----------
const taxonomy = () => [...new Set(S.data.jobs.flatMap(j => [...j.mandatory, ...j.preferred].map(r => r.skill)).concat(S.data.extraSkills))].sort();
function renderSkills() {
  const box = $('#skills');
  box.innerHTML = S.skills.length ? S.skills.map((s, i) => `<button class="chip ${s.confirmed ? 'ok' : ''}" data-i="${i}" title="${esc(s.evidence ? 'Evidence: “' + s.evidence + '”' : 'No quote from CV')}">${s.confirmed ? '✓ ' : ''}${esc(s.name)}<span class="x" data-del="${i}" aria-label="Remove">×</span></button>`).join('')
    + (S.method ? `<p class="mu sm" style="margin:4px 0 0">Suggested by ${S.method === 'ai' ? 'AI with quotes from your CV (hover a chip)' : 'keyword matching'}. Click a chip to confirm it.</p>` : '')
    : '<p class="mu sm">No skills yet. Extract from CV or add manually.</p>';
  $$('#skills [data-i]').forEach(b => b.onclick = e => {
    const del = e.target.dataset.del;
    if (del !== undefined) S.skills.splice(+del, 1); else S.skills[+b.dataset.i].confirmed = !S.skills[+b.dataset.i].confirmed;
    renderSkills();
  });
  const have = new Set(S.skills.map(s => s.name));
  $('#addSkill').innerHTML = taxonomy().filter(t => !have.has(t)).map(t => `<option>${esc(t)}</option>`).join('');
  $('#toReport').disabled = !S.skills.some(s => s.confirmed);
}
function initProfile() {
  $('#samples').innerHTML = S.data.samples.map(s => `<button class="btn soft small" data-s="${s.id}">Sample: ${esc(s.label)}</button>`).join('');
  $$('[data-s]').forEach(b => b.onclick = () => { const s = S.data.samples.find(x => x.id === b.dataset.s); $('#cv').value = s.cv; $('#role').value = s.role; toast('Sample profile loaded — now extract skills'); });
  $('#addBtn').onclick = () => { const v = $('#addSkill').value; if (v) { S.skills.push({ name: v, evidence: '', confirmed: true }); renderSkills(); } };
  $('#confirmAll').onclick = () => { S.skills.forEach(s => s.confirmed = true); renderSkills(); };
  $('#extract').onclick = async () => {
    const b = $('#extract'); $('#pErr').innerHTML = '';
    b.disabled = true; b.innerHTML = '<span class="spin"></span>Extracting…';
    try {
      const r = await api('/api/profile', { cvText: $('#cv').value });
      S.skills = r.skills; S.method = r.method;
      if (r.notice) $('#pErr').innerHTML = `<div class="notice">${esc(r.notice)}</div>`;
      if (!r.skills.length) $('#pErr').innerHTML += '<div class="notice">No known skills found. Add them manually on the right.</div>';
      renderSkills();
    } catch (e) { $('#pErr').innerHTML = `<div class="err">${esc(e.message)}</div>`; }
    b.disabled = false; b.textContent = 'Extract skills';
  };
  $('#pdf').onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    if (f.size > 5e6) return ($('#pdfNote').textContent = 'PDF is larger than 5 MB — paste text instead.');
    if (!window.pdfjsLib) return ($('#pdfNote').textContent = 'PDF reader unavailable — paste text instead.');
    try {
      pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      const pdf = await pdfjsLib.getDocument({ data: await f.arrayBuffer() }).promise; let text = '';
      for (let i = 1; i <= Math.min(pdf.numPages, 8); i++) text += (await (await pdf.getPage(i)).getTextContent()).items.map(x => x.str).join(' ') + '\n';
      if (text.trim().length < 50) { $('#pdfNote').textContent = 'No text found (scanned PDF?). Paste your CV text instead.'; return; }
      $('#cv').value = text.trim(); $('#pdfNote').textContent = `Read ${pdf.numPages} page(s) from ${f.name}`;
    } catch (err) { $('#pdfNote').textContent = 'Could not read this PDF. Paste your CV text instead.'; }
    e.target.value = '';
  };
  $('#toReport').onclick = () => { track('report_started'); S.report = compute(confirmed()); S.sim.clear(); S.gap = S.report.topGaps[0]?.skill || null; S.qs = null; S.evals = []; S.done.interview = 0; track('report_generated'); go('report'); };
  renderSkills();
}
const confirmed = () => new Set(S.skills.filter(s => s.confirmed).map(s => s.name));

// ---------- matching (deterministic, same snapshot) ----------
function compute(have) {
  const jobs = S.data.jobs, N = jobs.length, auth = $('#auth').value;
  const matches = jobs.map(j => {
    const missing = j.mandatory.filter(r => !have.has(r.skill)), matched = j.mandatory.filter(r => have.has(r.skill));
    const status = missing.length ? 'gap' : (j.workAuthRequired && auth !== 'yes') ? 'clarify' : 'fit';
    return { job: j, status, missing, matched, prefHave: j.preferred.filter(r => have.has(r.skill)) };
  });
  const demand = {};
  jobs.forEach(j => { j.mandatory.forEach(r => { (demand[r.skill] ||= { m: 0, p: 0, cites: [] }).m++; demand[r.skill].cites.push({ co: j.company, q: r.quote, url: j.sourceUrl }); });
    j.preferred.forEach(r => { (demand[r.skill] ||= { m: 0, p: 0, cites: [] }).p++; }); });
  const topGaps = Object.entries(demand).filter(([k, d]) => !have.has(k) && d.m > 0)
    .sort((a, b) => b[1].m - a[1].m || b[1].p - a[1].p).slice(0, 3)
    .map(([skill, d]) => ({ skill, demand: d.m / N, mCount: d.m, pCount: d.p, citations: d.cites.slice(0, 2) }));
  const c = k => matches.filter(m => m.status === k).length;
  return { sampleSize: N, snapshotDate: S.data.snapshot.date, matches, topGaps, fit: c('fit'), clarify: c('clarify'), gap: c('gap'), matchRate: c('fit') / N, enough: N >= 5 };
}

function renderReport() {
  const v = $('#v-report'), R = S.report;
  if (!R) { v.innerHTML = `<div class="card empty">No report yet.<br><br><button class="btn" onclick="go('profile')">Start with your profile →</button></div>`; return; }
  const snap = S.data.snapshot;
  const missingAll = [...new Set(R.matches.flatMap(m => m.missing.map(r => r.skill)))];
  const simR = S.sim.size ? compute(new Set([...confirmed(), ...S.sim])) : null;
  v.innerHTML = `
  <div class="card">
    <div class="row" style="justify-content:space-between"><div><h2>Career report: ${esc($('#role').value || 'Data Analyst')} → Senior Data Analyst</h2>
      <p class="mu sm" style="margin:0">Market: ${esc(snap.market)} · Snapshot ${esc(snap.date)} · ${R.sampleSize} postings · <b>${esc(snap.label)}</b></p></div>
      <button class="btn soft small" onclick="go('profile')">Edit skills</button></div>
    ${R.enough ? '' : '<div class="notice">Not enough data: fewer than 5 postings in this snapshot — results are indicative only.</div>'}
    <div class="kpis">
      <div class="kpi"><b>${R.fit}</b><span class="sm">Fit</span></div>
      <div class="kpi"><b>${R.clarify}</b><span class="sm">Need to clarify</span></div>
      <div class="kpi"><b>${R.gap}</b><span class="sm">Gap</span></div>
      <div class="kpi"><b>${pct(R.matchRate)}</b><span class="sm">Match rate (fit / ${R.sampleSize})</span></div>
    </div>
    <p class="mu sm" style="margin:0">${esc(snap.sourceNote)}</p>
  </div>
  <div class="grid2">
    <div class="card"><h2>Top ${R.topGaps.length} skill gaps</h2><p class="mu sm">Ranked by how many postings list the skill as <b>mandatory</b>.</p>
      ${R.topGaps.length ? R.topGaps.map((g, i) => `<div class="gapc"><div class="row" style="justify-content:space-between"><b>${i + 1}. ${esc(g.skill)}</b><span class="sm mu">mandatory in ${g.mCount}/${R.sampleSize} · preferred in ${g.pCount}</span></div>
        <div class="bar"><i style="width:${pct(g.demand)}"></i></div>
        ${g.citations.map(c => `<blockquote>“${esc(c.q)}” — ${esc(c.co)}</blockquote>`).join('')}
        <button class="btn small ${i ? 'soft' : ''}" data-gap="${esc(g.skill)}">Practice interview on ${esc(g.skill)} →</button></div>`).join('')
        : '<p>No mandatory gaps found in this snapshot. Try the interview on a skill you want to strengthen.</p>'}
    </div>
    <div class="card"><h2>Skill simulator</h2><p class="mu sm">What if you confirmed one more skill? Recalculated on the same ${R.sampleSize} postings.</p>
      ${missingAll.map(s => `<label class="row" style="padding:4px 0"><input type="checkbox" data-sim="${esc(s)}" ${S.sim.has(s) ? 'checked' : ''}> ${esc(s)}</label>`).join('') || '<p class="mu">Nothing to simulate — no missing mandatory skills.</p>'}
      ${simR ? `<div class="notice">With ${[...S.sim].map(esc).join(', ')}: <b>${simR.fit}</b> fit (${simR.fit - R.fit >= 0 ? '+' : ''}${simR.fit - R.fit}), match rate <b>${pct(simR.matchRate)}</b> vs ${pct(R.matchRate)} now.</div>` : ''}
    </div>
  </div>
  <div class="card"><h2>Postings</h2><p class="mu sm">Fit = all mandatory skills confirmed and no unknown requirement · Clarify = a mandatory fact is unknown · Gap = a mandatory skill is missing.</p>
    ${R.matches.map(m => `<div class="job"><div><div class="row"><b>${esc(m.job.company)}: ${esc(m.job.title)}</b><span class="st ${m.status}">${m.status === 'fit' ? 'Fit' : m.status === 'gap' ? 'Gap' : 'Clarify'}</span></div>
      <div class="sm mu">${esc(m.job.city)} · posted: ${esc(m.job.postingDate || 'not stated')} · salary: ${esc(m.job.salary || 'not stated')}</div>
      <div style="margin-top:6px">${m.matched.map(r => `<span class="tag have">✓ ${esc(r.skill)}</span>`).join('')}${m.missing.map(r => `<span class="tag miss">✗ ${esc(r.skill)}</span>`).join('')}${m.prefHave.map(r => `<span class="tag">+ ${esc(r.skill)} (preferred)</span>`).join('')}</div>
      ${m.status === 'clarify' ? '<div class="sm" style="color:var(--warn)">Need to clarify: US work authorization is required, yours is not stated.</div>' : ''}
      ${m.missing[0] ? `<blockquote>“${esc(m.missing[0].quote)}”</blockquote>` : ''}</div>
      <a class="sm" href="${esc(m.job.sourceUrl)}" target="_blank" rel="noopener">Similar real postings ↗</a></div>`).join('')}
  </div>`;
  $$('[data-gap]').forEach(b => b.onclick = () => { S.gap = b.dataset.gap; S.qs = null; S.evals = []; S.qi = 0; go('interview'); });
  $$('[data-sim]').forEach(c => c.onchange = () => { c.checked ? S.sim.add(c.dataset.sim) : S.sim.delete(c.dataset.sim); renderReport(); });
}

// ---------- interview ----------
let timer;
function renderInterview() {
  const v = $('#v-interview'); clearInterval(timer);
  if (!S.report) { v.innerHTML = `<div class="card empty">The interview checks the top gap from your report.<br><br><button class="btn" onclick="go('profile')">Build my report first →</button></div>`; return; }
  const gaps = S.report.topGaps.map(g => g.skill), opts = gaps.length ? gaps : [...confirmed()];
  if (!S.gap) S.gap = opts[0];
  if (!S.qs) {
    v.innerHTML = `<div class="card" style="max-width:760px;margin:0 auto 16px">
      <h2>AI practice interview</h2><p class="mu">2 short questions on your gap: one technical, one behavioral. Answer in text (4–8 sentences). Each answer is scored on a fixed rubric: technical correctness, reasoning, evidence, clarity (0–4 each).</p>
      <label class="sm mu">Skill to practice<select id="gapSel">${opts.map(g => `<option ${g === S.gap ? 'selected' : ''}>${esc(g)}</option>`).join('')}</select></label>
      <div class="row" style="margin-top:14px"><button class="btn" id="startI">Start interview</button><span class="mu sm">Formative feedback, not a hiring decision.</span></div><div id="iErr"></div></div>`;
    $('#gapSel').onchange = e => S.gap = e.target.value;
    $('#startI').onclick = async () => {
      const b = $('#startI'); b.disabled = true; b.innerHTML = '<span class="spin"></span>Generating questions…'; $('#iErr').innerHTML = '';
      try {
        const r = await api('/api/interview/questions', { targetSkill: S.gap, targetRole: 'Senior Data Analyst', skills: [...confirmed()] });
        S.qs = r.questions; S.qi = 0; S.evals = []; track('interview_started'); renderInterview();
      } catch (e) { $('#iErr').innerHTML = `<div class="err">${esc(e.message)} <button class="btn soft small" onclick="renderInterview()">Retry</button></div>`; b.disabled = false; b.textContent = 'Start interview'; }
    };
    return;
  }
  const q = S.qs[S.qi], ev = S.evals[S.qi];
  v.innerHTML = `<div style="max-width:860px;margin:0 auto">
    <div class="card"><div class="row" style="justify-content:space-between"><span class="st fit">Question ${S.qi + 1} of 2 · ${esc(q.questionType)} · ${esc(q.targetSkill)}</span><span class="mu sm" id="tm"></span></div>
      <h2 style="margin-top:10px">${esc(q.questionText)}</h2>
      <textarea id="ans" placeholder="Type your answer… Use a concrete example and say why you chose your approach." ${ev ? 'disabled' : ''}>${esc(ev?._answer || '')}</textarea>
      <div class="row" style="margin-top:10px">${ev ? '' : '<button class="btn" id="sub">Submit answer</button>'}<span class="mu sm" id="wc"></span></div><div id="iErr"></div></div>
    <div id="evalBox">${ev ? evalHtml(ev) : ''}</div>
    ${ev ? `<div class="row" style="justify-content:flex-end">${S.qi === 0 ? '<button class="btn" id="next">Next question →</button>' : '<button class="btn ac" onclick="go(\'plan\')">See my growth plan →</button>'}</div>` : ''}</div>`;
  const ta = $('#ans'), wc = () => $('#wc').textContent = ta.value.trim().split(/\s+/).filter(Boolean).length + ' words';
  ta.oninput = wc; wc();
  if (!ev) { const t0 = Date.now(); timer = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); $('#tm') && ($('#tm').textContent = `⏱ ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`); }, 1000); }
  $('#next') && ($('#next').onclick = () => { S.qi = 1; renderInterview(); });
  $('#sub') && ($('#sub').onclick = async () => {
    const answer = ta.value.trim();
    if (!answer) { $('#iErr').innerHTML = '<div class="err">Please write an answer first.</div>'; return; }
    const b = $('#sub'); b.disabled = true; b.innerHTML = '<span class="spin"></span>Evaluating…'; $('#iErr').innerHTML = '';
    try {
      const r = await api('/api/interview/evaluate', { question: q, answer }); r._answer = answer; S.evals[S.qi] = r;
      if (S.qi === 1) { S.done.interview = 1; track('interview_completed'); }
      clearInterval(timer); renderInterview(); nav();
    } catch (e) { $('#iErr').innerHTML = `<div class="err">${esc(e.message)} Your answer is kept — press Submit to retry.</div>`; b.disabled = false; b.textContent = 'Submit answer'; }
  });
}
function evalHtml(e) {
  return `<div class="card"><div class="row" style="gap:18px"><div class="score">${e.totalScore}%</div><div><b>Rubric score</b><br><span class="mu sm">Sum of 4 criteria / 16 · learning rubric, not a probability of being hired</span></div></div>
  ${e.shortAnswer ? '<div class="notice">Very short answer: there is not enough evidence to score higher.</div>' : ''}
  <div style="margin:12px 0">${e.rubricScores.map(r => `<div class="rub"><b class="sm">${esc(r.criterion)}</b><div><div class="bar"><i style="width:${r.score * 25}%"></i></div><span class="sm mu">${esc(r.explanation)}</span></div><b>${r.score}/4</b></div>`).join('')}</div>
  <div class="grid2"><div><h3>Strengths</h3><ul>${e.strengths.map(s => `<li>${esc(s)}</li>`).join('') || '<li class="mu">—</li>'}</ul></div>
  <div><h3>Missing points</h3><ul>${e.weaknesses.map(s => `<li>${esc(s)}</li>`).join('') || '<li class="mu">—</li>'}</ul></div></div>
  ${e.citedAnswerSegments.length ? `<h3>From your answer</h3>${e.citedAnswerSegments.map(c => `<blockquote>“${esc(c)}”</blockquote>`).join('')}` : ''}
  ${e.improvedStructure ? `<h3 style="margin-top:12px">A stronger structure</h3><p class="mu" style="white-space:pre-line;margin:0">${esc(e.improvedStructure)}</p>` : ''}</div>`;
}

// ---------- plan + feedback ----------
function renderPlan() {
  const v = $('#v-plan');
  if (!S.report) { v.innerHTML = `<div class="card empty">Your plan is built from the report and interview.<br><br><button class="btn" onclick="go('profile')">Start →</button></div>`; return; }
  const skill = S.gap || S.report.topGaps[0]?.skill, L = S.data.learning[skill];
  const ev = S.evals.filter(Boolean), pr = ev.length ? ev[ev.length - 1].recommendedPractice : null;
  const avg = ev.length ? Math.round(ev.reduce((a, e) => a + e.totalScore, 0) / ev.length) : null;
  const hours = $('#hours').value;
  v.innerHTML = `<div class="grid2">
   <div>
    <div class="card"><h2>Your next step: ${esc(skill || '—')}</h2>
      <p class="mu sm">Why: ${S.report.topGaps[0] ? `mandatory in ${S.report.topGaps.find(g => g.skill === skill)?.mCount ?? '—'} of ${S.report.sampleSize} postings` : 'chosen by you'}${avg !== null ? ` · interview rubric ${avg}%` : ' · interview not taken yet'} · study time ${esc(hours)}/week</p>
      ${pr && pr.title ? `<div class="gapc"><b>Today · ${pr.minutes} min practice: ${esc(pr.title)}</b><ol class="sm">${pr.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol><div class="sm"><b>Done when:</b> ${esc(pr.successCriterion)}</div></div>`
        : `<div class="notice">Take the AI interview to get a personal 20–40 min practice task. <button class="btn soft small" onclick="go('interview')">Go to interview</button></div>`}
      ${L ? `<div class="gapc"><b>This week · mini-project (~${L.hours} h)</b><p style="margin:6px 0">${esc(L.miniProject)}</p><div class="sm"><b>Done when:</b> ${esc(L.criterion)}</div>
        <div class="row" style="margin-top:10px"><a class="btn small" id="learn" href="${esc(L.url)}" target="_blank" rel="noopener" style="text-decoration:none">Open: ${esc(L.resource)} ↗</a></div></div>` : ''}
      <p class="mu sm" style="margin:0">Re-take the interview after the project to see your rubric change.</p>
    </div>
    <div class="card pro"><h3>Future Pro · $15–19 / month (not live)</h3><p class="mu sm" style="margin:0 0 10px">Monitoring of new postings for your target, more career goals, repeat interviews and progress over time. No payment is taken — we are only measuring interest.</p>
      <div class="row"><button class="btn small" data-pi="yes">I'd try Pro</button><button class="btn soft small" data-pi="maybe">Maybe later</button><button class="btn soft small" data-pi="no">Not for me</button></div></div>
   </div>
   <div class="card" id="fbCard"><h2>Was this useful?</h2><p class="mu sm">Anonymous. Helps us validate the product.</p>
      <div class="stars" id="fbStars"></div>
      <label class="row sm" style="margin:10px 0"><input type="checkbox" id="fbRet"> I'd come back for an updated report next month</label>
      <textarea id="fbCom" style="min-height:100px" placeholder="What would you use instead of this service? What blocked you?"></textarea>
      <div class="row" style="margin-top:10px"><button class="btn" id="fbSend">Send feedback</button></div>
   </div></div>`;
  $('#learn') && ($('#learn').onclick = () => track('learning_action_clicked'));
  $$('[data-pi]').forEach(b => b.onclick = () => { S.fb.pricing = b.dataset.pi; $$('[data-pi]').forEach(x => x.classList.toggle('soft', x !== b)); track('pricing_interest_' + b.dataset.pi); toast('Thanks — noted'); });
  const stars = () => { $('#fbStars').innerHTML = [1, 2, 3, 4, 5].map(i => `<button class="${i <= S.fb.rating ? 'on' : ''}" data-r="${i}" aria-label="${i} stars">★</button>`).join(''); $$('[data-r]').forEach(b => b.onclick = () => { S.fb.rating = +b.dataset.r; stars(); }); };
  stars();
  $('#fbSend').onclick = async () => {
    try {
      await api('/api/feedback', { sid, completedReport: !!S.report, interviewFinished: !!S.done.interview, helpfulRating: S.fb.rating || null, nextUpdateInterest: $('#fbRet').checked, pricingInterest: S.fb.pricing || '', comment: $('#fbCom').value });
      $('#fbCard').innerHTML = '<div class="empty"><h2>Thank you!</h2>Your feedback was saved anonymously.</div>';
    } catch (e) { toast(e.message); }
  };
}

// ---------- boot ----------
(async function () {
  nav();
  api('/api/health').then(h => { const a = $('#ai'); a.classList.toggle('on', h.ai); a.textContent = h.ai ? 'AI: on' : 'AI: off — add key to .env'; }).catch(() => $('#ai').textContent = 'Server offline');
  try { S.data = await api('/api/jobs'); initProfile(); } catch (e) { toast('Could not load job snapshot: ' + e.message); }
})();
