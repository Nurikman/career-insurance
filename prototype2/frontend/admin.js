// tirek admin: read-only view of feedback, users and CV data (with consent). Every request is audited server-side.
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const API = (window.API_BASE || '').replace(/\/$/, '');
const dt = t => t ? new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' ') : '—';
const k$ = n => n == null ? '—' : '$' + Math.round(n / 1000) + 'k';
let TOKEN = '';
try { TOKEN = sessionStorage.getItem('tirek-admin') || ''; } catch (e) {}

async function get(path) {
  const r = await fetch(API + path, { headers: { Authorization: 'Bearer ' + TOKEN } });
  const j = await r.json().catch(() => ({ error: 'Invalid response' }));
  if (!r.ok) throw Object.assign(new Error(j.error || 'Request failed'), { status: r.status });
  return j;
}
function lock(msg) {
  TOKEN = ''; try { sessionStorage.removeItem('tirek-admin'); } catch (e) {}
  $('#login').classList.remove('hide'); $('#tabs').classList.add('hide'); $('#out').classList.add('hide'); $('#view').innerHTML = '';
  $('#lerr').textContent = msg || '';
}
async function open(tab) {
  $$('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.t === tab));
  const v = $('#view'); v.innerHTML = '<div class="loading"><span class="spin"></span></div>';
  try { v.innerHTML = await ({ overview, feedback, users, audit })[tab](); bind(); }
  catch (x) { if (x.status === 401 || x.status === 403) lock(x.message); else v.innerHTML = `<div class="err">${esc(x.message)}</div>`; }
}

async function overview() {
  const o = await get('/api/admin/overview');
  return `<div class="kpis">
    <div class="blk blue"><div class="lbl">Users</div><div class="big">${o.users.n}</div></div>
    <div class="blk green"><div class="lbl">Reports</div><div class="big">${o.reports}</div></div>
    <div class="blk yellow"><div class="lbl">Avg usefulness</div><div class="big">${o.feedback.avg ?? '—'}</div><div class="sub">${o.feedback.n} responses</div></div>
    <div class="blk blue"><div class="lbl">CV consent</div><div class="big">${o.users.cv || 0}/${o.users.n}</div><div class="sub">research: ${o.users.research || 0}</div></div></div>
  <div class="grid3" style="margin-top:16px">
    <div class="card"><h2>Funnel</h2><table>${o.funnel.map(f => `<tr><td>${esc(f.name)}</td><td>${f.users} users</td><td>${f.n}</td></tr>`).join('') || '<tr><td class="mu">No events yet</td></tr>'}</table></div>
    <div class="card"><h2>Would buy Pro</h2><table>${o.buyPro.map(b => `<tr><td>${esc(b.answer || 'no answer')}</td><td>${b.n}</td></tr>`).join('') || '<tr><td class="mu">—</td></tr>'}</table></div>
    <div class="card"><h2>Countries</h2><table>${o.countries.map(c => `<tr><td>${esc(c.country)}</td><td>${c.n}</td></tr>`).join('') || '<tr><td class="mu">—</td></tr>'}</table></div></div>
  <p class="sm mu">CV text retention: ${o.retention.cvDays} days · consent version ${esc(o.retention.consentVersion)}</p>`;
}
async function feedback() {
  const f = await get('/api/admin/feedback');
  return `<div class="card"><h2>Feedback</h2><table><tr><th>Date</th><th>Rating</th><th>Buy Pro</th><th>Comment</th><th>Country</th><th>User ref</th></tr>
    ${f.items.map(x => `<tr><td>${dt(x.created_at)}</td><td>${x.rating ?? '—'}</td><td>${esc(x.buy_pro || '—')}</td><td>${esc(x.comment || '')}</td><td>${esc(x.country || 'deleted')}</td><td class="mu">${esc(x.user_ref || 'anonymous')}</td></tr>`).join('') || '<tr><td class="mu">No feedback yet</td></tr>'}</table></div>`;
}
async function users() {
  const u = await get('/api/admin/users');
  return `<div class="card"><h2>Users</h2><p class="sm mu">Masked list. Click a row to open full details (logged).</p><table>
    <tr><th>User</th><th>Email</th><th>Country</th><th>Joined</th><th>Last login</th><th>Reports</th><th>CV stored</th><th>Research</th></tr>
    ${u.items.map(x => `<tr class="click" data-u="${esc(x.id)}"><td>${esc(x.name)}</td><td>${esc(x.email)}</td><td>${esc(x.country)}</td><td>${dt(x.created_at)}</td><td>${dt(x.last_login_at)}</td><td>${x.reports}</td><td>${x.has_cv ? 'yes' : x.consent_store_cv ? 'consented' : 'no'}</td><td>${x.consent_research ? 'yes' : 'no'}</td></tr>`).join('') || '<tr><td class="mu">No users yet</td></tr>'}</table></div>`;
}
async function userDetail(id) {
  const d = await get('/api/admin/users/' + id), a = d.account;
  return `<button class="btn ghost small" data-back>← Users</button>
  <div class="grid2" style="margin-top:14px">
    <div class="card"><h2>${esc(a.name)} ${esc(a.surname)}</h2><table>
      <tr><td class="mu">Email</td><td>${esc(a.email)}</td></tr><tr><td class="mu">Country</td><td>${esc(a.country)}</td></tr>
      <tr><td class="mu">Joined</td><td>${dt(a.created_at)}</td></tr><tr><td class="mu">Last login</td><td>${dt(a.last_login_at)}</td></tr>
      <tr><td class="mu">Consents</td><td>CV ${a.consent_store_cv ? 'yes' : 'no'} · research ${a.consent_research ? 'yes' : 'no'} · v${esc(a.consent_version)}</td></tr>
      <tr><td class="mu">Goal</td><td>${esc(d.profile.current_role || '—')} → ${esc(d.profile.target_role || '—')} · ${esc(d.profile.target_salary || '')} · ${esc(d.profile.study_hours || '')}</td></tr></table></div>
    <div class="card"><h2>Reports</h2><table><tr><th>Date</th><th>Target</th><th>Risk</th><th>Value</th></tr>
      ${d.reports.map(r => `<tr><td>${esc(r.createdAt.slice(0, 10))}</td><td>${esc(r.targetRole)}</td><td>${r.score}</td><td>${k$(r.value.min)}–${k$(r.value.max)}</td></tr>`).join('') || '<tr><td class="mu">—</td></tr>'}</table></div></div>
  <div class="card"><h2>CV</h2>${d.cv ? `<p class="sm mu">${esc(d.cv.name || 'no file')} · saved ${dt(d.cv.savedAt)}</p>${d.cv.about ? `<h3>About</h3><pre>${esc(d.cv.about)}</pre>` : ''}${d.cv.text ? `<h3>CV text</h3><pre>${esc(d.cv.text)}</pre>` : ''}` : `<p class="mu">${esc(d.cvNote || 'No CV text stored.')}</p>`}
    ${d.extracted ? `<details><summary>Extracted profile (from latest report)</summary><pre>${esc(JSON.stringify(d.extracted, null, 2))}</pre></details>` : ''}</div>
  <div class="card"><h2>Feedback</h2>${d.feedback.map(f => `<div class="sm">${dt(f.created_at)} · ${f.rating ?? '—'}★ · ${esc(f.buy_pro || '')} · ${esc(f.comment || '')}</div>`).join('') || '<p class="mu">—</p>'}</div>`;
}
async function audit() {
  const a = await get('/api/admin/audit');
  return `<div class="card"><h2>Access log</h2><p class="sm mu">Every admin request, including denied attempts.</p><table><tr><th>Time (UTC)</th><th>Action</th><th>Target</th><th>IP</th></tr>
    ${a.items.map(x => `<tr><td>${dt(x.created_at)}</td><td>${esc(x.action)}</td><td>${esc(x.target || '')}</td><td class="mu">${esc(x.ip || '')}</td></tr>`).join('')}</table></div>`;
}
function bind() {
  $$('[data-u]').forEach(r => r.onclick = async () => {
    const v = $('#view'); v.innerHTML = '<div class="loading"><span class="spin"></span></div>';
    try { v.innerHTML = await userDetail(r.dataset.u); bind(); } catch (x) { v.innerHTML = `<div class="err">${esc(x.message)}</div>`; }
  });
  $('[data-back]') && ($('[data-back]').onclick = () => open('users'));
}

$('#login').onsubmit = async e => {
  e.preventDefault(); TOKEN = $('#tok').value.trim(); $('#lerr').textContent = '';
  try { await get('/api/admin/overview'); } catch (x) { return lock(x.message); }
  try { sessionStorage.setItem('tirek-admin', TOKEN); } catch (e) {}
  $('#login').classList.add('hide'); $('#tabs').classList.remove('hide'); $('#out').classList.remove('hide'); $('#tok').value = '';
  open('overview');
};
$$('#tabs button').forEach(b => b.onclick = () => open(b.dataset.t));
$('#out').onclick = () => lock('');
if (TOKEN) { $('#login').classList.add('hide'); $('#tabs').classList.remove('hide'); $('#out').classList.remove('hide'); open('overview'); }
