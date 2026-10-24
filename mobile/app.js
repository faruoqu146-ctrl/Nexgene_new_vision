const API = window.location.origin.replace(/\/$/, '');
const $ = id => document.getElementById(id);
const FOUNDER_EMAIL = 'faruoqu146@gmail.com';

let csrf = '';
let mode = '';
let idx = 0;
let data = {};
let authMode = 'login';
let googleReady = false;

async function api(path, options = {}) {
  const opts = {
    credentials: 'include',
    ...options,
    headers: { ...(options.headers || {}) },
  };
  if (opts.body && !opts.headers['Content-Type']) opts.headers['Content-Type'] = 'application/json';
  if (opts.method && opts.method !== 'GET' && opts.method !== 'HEAD') {
    if (!csrf) csrf = (document.cookie.match(/(?:^|;\s*)nexgene_csrf=([^;]*)/) || [])[1] || '';
    if (csrf) opts.headers['X-CSRF-Token'] = decodeURIComponent(csrf);
  }
  return fetch(API + path, opts);
}

function setMsg(id, text) { const el = $(id); if (el) el.textContent = text; }

async function ensureAuthed() {
  try { await api('/api/v1/auth/csrf'); } catch (e) {}
  csrf = (document.cookie.match(/(?:^|;\s*)nexgene_csrf=([^;]*)/) || [])[1] || '';
  csrf = csrf ? decodeURIComponent(csrf) : '';
  if (!csrf) return null;
  try {
    const r = await api('/api/v1/auth/me');
    if (!r.ok) { csrf = ''; return null; }
    return await r.json();
  } catch (e) { return null; }
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
      if ($('auth')) $('auth').classList.remove('hide');
      return;
    }
    if (!r.ok) {
      setMsg('profilemsg', d.detail || 'Could not save your context.');
      return;
    }
    if ($('onboarding')) $('onboarding').classList.add('hide');
    setMsg('profilemsg', 'Context saved.');
  } catch (e) {
    setMsg('profilemsg', 'Could not save your context right now.');
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
    ['age_range', 'country', 'occupation', 'study_field', 'schedule', 'timezone'].forEach(k => {
      if ($(k)) $(k).value = p[k] || '';
    });
    if ($('student')) $('student').value = p.student === true ? 'yes' : p.student === false ? 'no' : '';
  } else if ($('onboarding')) {
    $('onboarding').classList.add('hide');
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
}

async function submitAuth() {
  const email = ($('email') && $('email').value || '').trim().toLowerCase();
  const password = ($('password') && $('password').value) || '';
  if (!email || password.length < 12) {
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

function setAuthMode(next) {
  authMode = next;
  const reg = next === 'register';
  if ($('tabLogin')) $('tabLogin').classList.toggle('active', !reg);
  if ($('tabRegister')) $('tabRegister').classList.toggle('active', reg);
  if ($('authTitle')) $('authTitle').textContent = reg ? 'Create your baseline.' : 'Welcome back.';
  if ($('authPrimary')) $('authPrimary').textContent = reg ? 'Create account' : 'Sign in';
  setMsg('authmsg', '');
}
function register() { setAuthMode('register'); }
function login() { setAuthMode('login'); }

async function account() {
  if (csrf) {
    await api('/api/v1/auth/logout', { method: 'POST' });
    csrf = '';
    location.reload();
  } else if ($('auth')) {
    $('auth').classList.remove('hide');
    setAuthMode('login');
  }
}

async function boot() {
  const me = await ensureAuthed();
  if (me && me.id) {
    if ($('account')) $('account').textContent = 'Sign out';
    await loadProfile();
  } else {
    csrf = '';
  }
}

// Expose handlers used by HTML onclick attributes
window.saveProfile = saveProfile;
window.submitAuth = submitAuth;
window.register = register;
window.login = login;
window.account = account;
window.setAuthMode = setAuthMode;

boot();
