const API = window.location.origin.replace(/\/$/, '');
const $ = id => document.getElementById(id);
const FOUNDER_EMAIL = 'faruoqu146@gmail.com';

let csrf = '';
let mode = '';
let idx = 0;
let data = {};
let authMode = 'login';
let googleReady = false;

const M = [
  ['sleep_duration', 'How long did you sleep?', 'Pick the window that feels closest.', [['\u25d1', 'Under 5h', 4.5], ['\u25d1', '5-6h', 5.5], ['\u25d2', '6-7h', 6.5], ['\u25d5', '7-8h', 7.5], ['\u25c9', '8-9h', 8.5], ['\u2726', '9h+', 9.5]]],
  ['sleep_quality', 'How did your sleep feel?', 'No scorekeeping. Just your read.', [['\u2639', 'Rough', 2], ['\u25d1', 'Restless', 4], ['\u25d1', 'Okay', 6], ['\u25d5', 'Good', 8], ['\u263a', 'Deep', 10]]],
  ['energy', 'How are you arriving today?', 'First instinct.', [['\ud83e\udeab', 'Drained', 2], ['\u25d1', 'Low', 4], ['\u25d1', 'Steady', 6], ['\u25d5', 'Good', 8], ['\u26a1', 'Charged', 10]]],
  ['morning_context', 'Anything unusual?', 'Optional. You can always skip.', [['\u25cb', 'Nothing unusual', 'none'], ['\u25cc', 'Headache', 'headache'], ['\u2301', 'Fatigue', 'fatigue'], ['\u25b3', 'Pain', 'pain'], ['\u2192', 'Skip', 'skipped']]]
];

const E = [
  ['mood', 'How was today?', 'The overall texture of the day.', [['\u2639', 'Low', 2], ['\u25d1', 'Heavy', 4], ['\u25d1', 'Mixed', 6], ['\u25d5', 'Good', 8], ['\u263a', 'Great', 10]]],
  ['stress', 'Where was your stress?', "Today's signal, not a diagnosis.", [['\u25cb', 'Very low', 1], ['\u25d1', 'Low', 3], ['\u25d1', 'Moderate', 5], ['\u25d5', 'High', 7], ['\u25cf', 'Very high', 9]]],
  ['focus', 'How was your focus?', 'How easy was it to stay with things?', [['\u2601', 'Scattered', 2], ['\u25d1', 'Patchy', 4], ['\u25d1', 'Okay', 6], ['\u25d5', 'Strong', 8], ['\u25ce', 'Locked in', 10]]],
  ['activity_level', 'How much did you move?', 'Minutes can come later.', [['\u25cb', 'Very little', 2], ['\u25d1', 'Light', 4], ['\u25d1', 'Moderate', 6], ['\u25d5', 'A lot', 8], ['\u2192', 'Skip', 0]]],
  ['diet_quality', 'How did you eat?', 'Think balance, not calories.', [['\u00b7', 'Chaotic', 2], ['\u25d1', 'Mostly quick', 4], ['\u25d1', 'Mixed', 6], ['\u25d5', 'Mostly balanced', 8], ['\u2726', 'Very balanced', 10]]],
  ['caffeine', 'Caffeine today?', 'Coffee, tea and energy drinks count.', [['\u25cb', 'None', 0], ['\u25d1', '1', 1], ['\u25d1', '2', 2], ['\u25d5', '3+', 3]]],
  ['alcohol', 'Alcohol today?', 'Optional, no judgement.', [['\u25cb', 'None', 0], ['\u25d1', '1', 1], ['\u25d1', '2', 2], ['\u25d5', '3+', 3]]],
  ['nicotine', 'Nicotine / smoking?', 'Optional context for your baseline.', [['\u25cb', 'None', 0], ['\u25d1', 'Some', 2], ['\u25d5', 'Frequent', 5]]]
];

function node(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
function setMsg(id, text) { const el = $(id); if (el) el.textContent = text; }

function readCookie(name) {
  const parts = document.cookie ? document.cookie.split(';') : [];
  for (const part of parts) {
    const p = part.trim();
    if (p.startsWith(name + '=')) return decodeURIComponent(p.slice(name.length + 1));
  }
  return '';
}
function syncCsrfFromCookie() { csrf = readCookie('nexgene_csrf') || ''; return csrf; }

async function api(path, options = {}) {
  const opts = { credentials: 'include', ...options, headers: { ...(options.headers || {}) } };
  if (opts.body && !opts.headers['Content-Type']) opts.headers['Content-Type'] = 'application/json';
  if (opts.method && opts.method !== 'GET' && opts.method !== 'HEAD') {
    if (!csrf) syncCsrfFromCookie();
    if (csrf) opts.headers['X-CSRF-Token'] = csrf;
  }
  return fetch(API + path, opts);
}

function setAuthMode(next) {
  authMode = next;
  const reg = next === 'register';
  if ($('tabLogin')) $('tabLogin').classList.toggle('active', !reg);
  if ($('tabRegister')) $('tabRegister').classList.toggle('active', reg);
  if ($('authTitle')) $('authTitle').textContent = reg ? 'Create your baseline.' : 'Welcome back.';
  if ($('authLead')) $('authLead').textContent = reg ? 'A private place for your signals to become useful.' : 'Your baseline is waiting where you left it.';
  if ($('authPrimary')) $('authPrimary').textContent = reg ? 'Create account' : 'Sign in';
  if ($('passwordRules')) $('passwordRules').classList.toggle('hide', !reg);
  if ($('password')) $('password').setAttribute('autocomplete', reg ? 'new-password' : 'current-password');
  setMsg('authmsg', '');
}
function register() { setAuthMode('register'); }
function login() { setAuthMode('login'); }
function togglePassword() {
  const input = $('password');
  const button = document.querySelector('.passwordField button');
  if (!input || !button) return;
  const shown = input.type === 'text';
  input.type = shown ? 'password' : 'text';
  button.textContent = shown ? 'Show' : 'Hide';
}

async function refreshSession() {
  try { await api('/api/v1/auth/csrf'); } catch (e) {}
  syncCsrfFromCookie();
  return csrf;
}
async function ensureAuthed() {
  await refreshSession();
  if (!csrf) return null;
  try {
    const r = await api('/api/v1/auth/me');
    if (!r.ok) { csrf = ''; return null; }
    return await r.json();
  } catch (e) { return null; }
}

async function account() {
  if (csrf) {
    const r = await api('/api/v1/auth/logout', { method: 'POST' });
    if (r.ok) { csrf = ''; if ($('account')) $('account').textContent = 'Sign in'; location.reload(); }
  } else {
    if ($('auth')) $('auth').classList.remove('hide');
    setAuthMode('login');
  }
}

async function finishAuth(emailHint) {
  const me = await ensureAuthed();
  if (!me || !me.id) {
    setMsg('authmsg', 'Signed in on the server, but the browser session cookie was not kept. Stay on HTTPS and try again.');
    if ($('auth')) $('auth').classList.remove('hide');
    return;
  }
  if ($('auth')) $('auth').classList.add('hide');
  if ($('account')) $('account').textContent = 'Sign out';
  await loadProfile();
  await load();
}

async function submitAuth() {
  const email = ($('email') && $('email').value || '').trim().toLowerCase();
  const password = ($('password') && $('password').value) || '';
  if (!email || password.length < 12 || !/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/[0-9]/.test(password) || !/[^A-Za-z0-9]/.test(password)) {
    setMsg('authmsg', 'Use a valid email and a 12+ character password with upper, lower, number and symbol.');
    return;
  }
  setMsg('authmsg', '');
  if ($('authPrimary')) $('authPrimary').disabled = true;
  try {
    const path = authMode === 'register' ? '/api/v1/auth/register' : '/api/v1/auth/login';
    const r = await api(path, { method: 'POST', body: JSON.stringify({ email, password }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { setMsg('authmsg', d.detail || 'Could not authenticate.'); return; }
    await finishAuth(email);
  } catch (e) {
    setMsg('authmsg', 'NexGene could not reach the server right now.');
  } finally {
    if ($('authPrimary')) $('authPrimary').disabled = false;
  }
}

async function loadProfile() {
  const r = await api('/api/v1/profile');
  if (r.status === 401) {
    csrf = '';
    if ($('auth')) $('auth').classList.remove('hide');
    setMsg('authmsg', 'Authentication required. Please sign in again.');
    return;
  }
  const d = r.ok ? await r.json() : { complete: false, profile: {} };
  if (!d.complete) {
    if ($('onboarding')) $('onboarding').classList.remove('hide');
    const p = d.profile || {};
    ['age_range', 'country', 'occupation', 'study_field', 'schedule', 'timezone'].forEach(k => { if ($(k)) $(k).value = p[k] || ''; });
    if ($('student')) $('student').value = p.student === true ? 'yes' : p.student === false ? 'no' : '';
  } else if ($('onboarding')) {
    $('onboarding').classList.add('hide');
  }
}

async function saveProfile() {
  const me = await ensureAuthed();
  if (!me || !me.id) {
    setMsg('profilemsg', 'Authentication required. Please sign in again.');
    if ($('auth')) $('auth').classList.remove('hide');
    return;
  }
  const payload = {
    age_range: (($('age_range') && $('age_range').value) || '').trim() || null,
    country: (($('country') && $('country').value) || '').trim() || null,
    occupation: (($('occupation') && $('occupation').value) || '').trim() || null,
    student: !$('student') || $('student').value === '' ? null : $('student').value === 'yes',
    study_field: (($('study_field') && $('study_field').value) || '').trim() || null,
    schedule: (($('schedule') && $('schedule').value) || '') || null,
    timezone: (($('timezone') && $('timezone').value) || '').trim() || null,
  };
  try {
    const r = await api('/api/v1/profile', { method: 'PUT', body: JSON.stringify(payload) });
    const d = await r.json().catch(() => ({}));
    if (r.status === 401) {
      setMsg('profilemsg', 'Authentication required. Please sign in again.');
      if ($('auth')) $('auth').classList.remove rec('hide');
      return;
    }
    if (!r.ok) { setMsg('profilemsg', d.detail || 'Could not save your context.'); return; }
    if ($('onboarding')) $('onboarding').classList.add('hide');
    setMsg('profilemsg', 'Context saved.');
  } catch (e) {
    setMsg('profilemsg', 'Could not save your context right now.');
  }
}

function start(m) {
  if (!csrf) {
    if ($('auth')) $('auth').classList.remove('hide');
    setMsg('authmsg', 'Create an account first. Your check-ins need somewhere private to live.');
    return;
  }
  mode = m; idx = 0; data = {};
  if ($('sheet')) $('sheet').classList.remove('hide');
  render();
}

function render() {
  const arr = mode === 'morning' ? M : E;
  const item = arr[idx];
  if ($('step')) $('step').textContent = (idx + 1) + ' / ' + arr.length;
  const q = $('q'); if (!q) return;
  clear(q);
  q.append(node('div', 'k', mode + ' check-in'), node('h3', null, item[1]), node('p', null, item[2]));
  const choices = $('choices'); clear(choices);
  item[3].forEach(o => {
    const b = node('button', 'choice');
    b.append(node('i', null, o[0]), node('b', null, o[1]));
    b.onclick = () => {
      choices.querySelectorAll('.choice').forEach(x => x.classList.remove('sel'));
      b.classList.add('sel');
      data[item[0]] = o[2];
      if ($('next')) $('next').disabled = false;
    };
    choices.appendChild(b);
  });
  if ($('next')) {
    $('next').disabled = data[item[0]] === undefined;
    $('next').textContent = idx === arr.length - 1 ? 'Save' : 'Continue';
  }
}

async function nextStep() {
  const arr = mode === 'morning' ? M : E;
  if (idx < arr.length - 1) { idx++; render(); return; }
  const r = await api('/api/v1/checkins/' + mode, { method: 'POST', body: JSON.stringify({ values: data }) });
  if (!r.ok) { alert('Could not save this check-in.'); return; }
  closeSheet();
  await load();
}

function closeSheet() { if ($('sheet')) $('sheet').classList.add('hide'); }

async function get(p) {
  if (!csrf && !syncCsrfFromCookie()) return {};
  const r = await api(p);
  if (r.status === 401) {
    csrf = '';
    if ($('account')) $('account').textContent = 'Sign in';
    if ($('auth')) $('auth').classList.remove('hide');
    setMsg('authmsg', 'Your session expired. Please sign in again.');
    return {};
  }
  return r.ok ? r.json() : {};
}

function showView(v) {
  ['today', 'patterns', 'timeline', 'report'].forEach(x => {
    const view = $(x + 'View');
    if (view) view.classList.toggle('hide', x !== v);
    const n = $('n' + x[0].toUpperCase() + x.slice(1));
    if (n) n.classList.toggle('active', x === v);
  });
  if (v === 'patterns') loadPatterns();
  if (v === 'timeline') loadTimeline();
  if (v === 'report') loadReport();
}

async function loadSignals() {
  const d = await get('/api/v1/signals');
  const box = $('signals'); if (!box) return;
  clear(box);
  (d.signals || []).forEach((sig, i) => {
    const card = node('div', 'signal');
    card.append(node('small', null, i === 0 ? 'NEXGENE SIGNAL' : 'SIGNAL'), node('b', null, sig.title), node('span', null, sig.body));
    if (sig.action === 'check_in') {
      const b = node('button', null, 'CHECK IN');
      b.onclick = () => start(new Date().getHours() < 15 ? 'morning' : 'evening');
      card.appendChild(b);
    } else if (sig.action === 'patterns') {
      const b = node('button', null, 'SEE PATTERNS');
      b.onclick = () => showView('patterns');
      card.appendChild(b);
    }
    box.appendChild(card);
  });
  if (!box.firstChild) {
    const e = node('div', 'empty');
    e.append(node('b', null, 'The Raven is watching quietly.'), node('span', null, 'Keep a little signal coming and something will appear here.'));
    box.appendChild(e);
  }
}

async function load() {
  if (!csrf && !syncCsrfFromCookie()) return;
  const d = await get('/api/v1/today');
  const keys = [['sleep_duration','SLEEP',v=>v+'h'],['energy','ENERGY',v=>v+'/10'],['mood','MOOD',v=>v+'/10'],['stress','STRESS',v=>v+'/10'],['focus','FOCUS',v=>v+'/10'],['diet_quality','EATING',v=>v+'/10']];
  const snapshot = $('snapshot');
  if (snapshot) {
    clear(snapshot);
    let count = 0;
    keys.forEach(x => {
      if (d[x[0]] !== undefined) {
        count++;
        const m = node('div', 'metric');
        m.append(node('small', null, x[1]), node('b', null, x[2](d[x[0]])));
        snapshot.appendChild(m);
      }
    });
    if (!snapshot.firstChild) {
      const e = node('div', 'empty');
      e.append(node('b', null, 'A quiet page.'), node('span', null, 'Two tiny check-ins begin the picture.'));
      snapshot.appendChild(e);
    }
    if ($('count')) $('count').textContent = Math.min(count, 2) + ' / 2 check-ins';
    if ($('bar')) $('bar').style.width = (Math.min(count, 2) * 50) + '%';
  }
  const ins = await get('/api/v1/insights');
  if ($('insight')) $('insight').textContent = (ins.items && ins.items[0]) || 'Your baseline is beginning to take shape.';
  if ($('account')) $('account').textContent = 'Sign out';
  await loadSignals();
}

async function loadPatterns() {
  const d = await get('/api/v1/patterns');
  const cards = $('patternCards'); if (!cards) return;
  clear(cards);
  [['sleep_duration','Sleep','h'],['sleep_quality','Sleep quality','/10'],['energy','Energy','/10'],['stress','Stress','/10'],['focus','Focus','/10']].forEach(([k,l,u]) => {
    if (d.averages && d.averages[k] !== undefined) {
      const p = node('div', 'pattern');
      p.append(node('small', null, l), node('b', null, d.averages[k] + u), node('span', null, '30 day average'));
      cards.appendChild(p);
    }
  });
  if (!cards.firstChild) {
    const e = node('div', 'empty');
    e.append(node('b', null, 'Still gathering signal.'), node('span', null, 'Keep checking in and the pattern view will wake up.'));
    cards.appendChild(e);
  }
  const chart = $('chart'); if (!chart) return;
  clear(chart);
  (d.series || []).slice(-14).forEach(p => {
    const day = node('div', 'day'); const bars = node('div', 'bars');
    const sleep = node('i'); const focus = node('i');
    sleep.style.height = (((p.sleep_duration || 0) / 10) * 100) + '%';
    focus.style.height = (((p.focus || 0) / 10) * 100) + '%';
    bars.append(sleep, focus);
    day.append(bars, node('small', null, (p.date || '').slice(5)));
    chart.appendChild(day);
  });
  if (!chart.firstChild) chart.append(node('div', 'empty', 'No chart yet.'));
}

async function loadTimeline() {
  const rows = await get('/api/v1/timeline');
  const timeline = $('timeline'); if (!timeline) return;
  clear(timeline);
  (Array.isArray(rows) ? rows : []).slice(0, 60).forEach(r => {
    const e = node('div', 'event');
    e.append(node('span', null, new Date(r.recorded_at).toLocaleDateString()), node('b', null, String(r.kind || '').replaceAll('_', ' ')), node('em', null, String(r.value)));
    timeline.appendChild(e);
  });
  if (!timeline.firstChild) {
    const e = node('div', 'empty');
    e.append(node('b', null, 'No observations yet.'), node('span', null, 'Your first check-in will appear here.'));
    timeline.appendChild(e);
  }
}

async function loadReport() {
  const d = await get('/api/v1/reports/weekly');
  const box = $('reportContent'); if (!box) return;
  clear(box);
  if (d.status === 'not_ready') {
    const hero = node('div', 'reportHero');
    hero.append(node('p', null, d.message || 'Not enough signal yet for a weekly read.'));
    box.appendChild(hero);
    return;
  }
  const hero = node('div', 'reportHero');
  hero.append(node('div', 'eyebrow', ((d.coverage && d.coverage.days) || '-') + ' DAYS OF SIGNAL'), node('h2', null, d.title || 'Your week with NexGene'), node('p', null, d.subtitle || ''));
  box.appendChild(hero);
  (d.sections || []).forEach(sec => {
    const card = node('article', 'reportCard');
    card.append(node('small', null, (sec.kind && sec.kind.toUpperCase()) || 'NOTE'), node('h3', null, sec.title), node('p', null, sec.body));
    box.appendChild(card);
  });
  box.appendChild(node('p', 'reportNote', d.disclaimer || ''));
}

async function boot() {
  try {
    const d = new Date();
    if ($('date')) $('date').textContent = d.toLocaleDateString(undefined, { day: '2-digit', month: 'short' }).toUpperCase();
    if ($('greeting')) $('greeting').textContent = d.getHours() < 12 ? 'Good morning,' : d.getHours() < 18 ? 'Good afternoon,' : 'Good evening,';
  } catch (e) {}
  const me = await ensureAuthed();
  if (me && me.id) {
    if ($('account')) $('account').textContent = 'Sign out';
    await loadProfile();
    await load();
  } else {
    csrf = '';
  }
}

window.start = start;
window.nextStep = nextStep;
window.closeSheet = closeSheet;
window.showView = showView;
window.saveProfile = saveProfile;
window.submitAuth = submitAuth;
window.register = register;
window.login = login;
window.account = account;
window.setAuthMode = setAuthMode;
window.togglePassword = togglePassword;

boot();
