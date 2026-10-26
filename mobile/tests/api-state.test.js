// Run: node --test mobile/tests/   (Node >= 18, no dependencies)
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { apiRequest, messageFor } = require('../api-state.js');

const resp = (status, body, headers = {}, raw) => ({
  ok: status >= 200 && status < 300, status,
  headers: { get: (k) => headers[k] ?? headers[k.toLowerCase()] ?? null },
  json: async () => { if (raw) throw new SyntaxError('Unexpected token <'); return body; },
});
const fetchOf = (r) => async () => r;

test('HTTP 401 -> unauthorized, not retryable', async () => {
  const r = await apiRequest('/x', { fetchImpl: fetchOf(resp(401, { detail: 'nope' })) });
  assert.equal(r.state, 'unauthorized'); assert.equal(r.retryable, false);
});
test('HTTP 403 -> forbidden', async () => {
  assert.equal((await apiRequest('/x', { fetchImpl: fetchOf(resp(403, {})) })).state, 'forbidden');
});
test('HTTP 429 -> rate_limited, retryable, retry-after surfaced', async () => {
  const r = await apiRequest('/x', { fetchImpl: fetchOf(resp(429, { code: 'engine_cooldown', retry_after_seconds: 42 })) });
  assert.equal(r.state, 'rate_limited'); assert.equal(r.retryable, true); assert.equal(r.retryAfter, 42);
  assert.match(messageFor(r).body, /42s/);
});
test('HTTP 500 -> failed (NOT empty), retryable, request id kept, raw detail never exposed', async () => {
  const r = await apiRequest('/x', { fetchImpl: fetchOf(resp(500, { detail: 'sqlalchemy.exc.OperationalError /app/db.py' }, { 'X-Request-ID': 'abc123' })) });
  assert.equal(r.state, 'failed'); assert.equal(r.retryable, true); assert.equal(r.requestId, 'abc123');
  const m = JSON.stringify(messageFor(r)); assert.ok(!/sqlalchemy|\/app\//.test(m));
});
test('network disconnection -> failed/network, not empty', async () => {
  const r = await apiRequest('/x', { fetchImpl: async () => { throw new TypeError('Failed to fetch'); } });
  assert.equal(r.state, 'failed'); assert.equal(r.category, 'network'); assert.equal(r.retryable, true);
});
test('timeout -> timed_out', async () => {
  const hang = (_u, o) => new Promise((_, rej) => o.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), { name: 'AbortError' }))));
  const r = await apiRequest('/x', { fetchImpl: hang, timeoutMs: 30 });
  assert.equal(r.state, 'timed_out'); assert.equal(r.retryable, true);
});
test('malformed JSON on 200 -> failed/malformed_response', async () => {
  const r = await apiRequest('/x', { fetchImpl: fetchOf(resp(200, null, {}, true)) });
  assert.equal(r.state, 'failed'); assert.equal(r.category, 'malformed_response');
});
test('payload failing validation -> failed, never treated as empty', async () => {
  const r = await apiRequest('/x', { fetchImpl: fetchOf(resp(200, { surprise: 1 })), validate: Array.isArray });
  assert.equal(r.state, 'failed'); assert.equal(r.category, 'malformed_response');
});
test('valid empty dataset -> empty', async () => {
  const r = await apiRequest('/x', { fetchImpl: fetchOf(resp(200, [])), validate: Array.isArray, isEmpty: (d) => d.length === 0 });
  assert.equal(r.state, 'empty');
});
test('valid data -> ready', async () => {
  const r = await apiRequest('/x', { fetchImpl: fetchOf(resp(200, [1])), validate: Array.isArray, isEmpty: (d) => d.length === 0 });
  assert.equal(r.state, 'ready'); assert.deepEqual(r.data, [1]);
});

// ---- render-level checks against the REAL loadTimeline / loadReport code, with a minimal fake DOM ----
function makeEl(tag) {
  const el = { tag, className: '', textContent: '', children: [], dataset: {}, onclick: null,
    classList: { add(c) { el.className += ' ' + c; }, remove() {}, toggle() {} },
    get firstChild() { return el.children[0] || null; },
    appendChild(c) { el.children.push(c); return c; }, append(...cs) { cs.forEach((c) => el.children.push(c)); },
    insertBefore(c) { el.children.unshift(c); }, removeChild(c) { el.children.splice(el.children.indexOf(c), 1); }, remove() {},
    querySelector(sel) { const cls = sel.split(',').map((s) => s.replace('.', '')); const walk = (n) => { for (const c of n.children) { if (cls.some((k) => (c.className || '').split(' ').includes(k))) return c; const d = walk(c); if (d) return d; } return null; }; return walk(el); } };
  return el;
}
function textOf(el) { return [el.textContent, ...el.children.map(textOf)].join(' '); }

function loadUi(fetchImpl) {
  const src = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');
  const grab = (a, b) => src.slice(src.indexOf(a), src.indexOf(b));
  const code = [
    grab('function node(', 'function setMsg('),
    grab('function sessionExpired(', 'async function loadReport('),
    grab('async function loadReport(', 'async function configureAI('),
  ].join('\n');
  const els = { timeline: makeEl('div'), reportContent: makeEl('div'), account: makeEl('b'), auth: makeEl('div'), authmsg: makeEl('p') };
  const ctx = { API: '', csrf: 'x', $: (id) => els[id], setMsg: (id, t) => { els[id].textContent = t; }, get: async () => ({}), configureAI() {},
    document: { createElement: makeEl }, NexGeneApi: { apiRequest: (u, o) => apiRequest(u, { ...o, fetchImpl }), messageFor }, Array, String, Date, Promise };
  vm.createContext(ctx);
  vm.runInContext(code + '\nthis.loadTimeline=loadTimeline;this.loadReport=loadReport;', ctx);
  return { ctx, els };
}

test('UI: a 500 on the weekly report shows a failure card, never a fabricated report', async () => {
  const { ctx, els } = loadUi(fetchOf(resp(500, { detail: 'boom' }, { 'X-Request-ID': 'r-1' })));
  await ctx.loadReport();
  const t = textOf(els.reportContent);
  assert.match(t, /Something went wrong/); assert.match(t, /TRY AGAIN/); assert.match(t, /r-1/);
  assert.ok(!/undefined|DAYS OF SIGNAL|Keep the signal coming/.test(t));
});
test('UI: 429 on the report is rate-limited, not an empty report', async () => {
  const { ctx, els } = loadUi(fetchOf(resp(429, { retry_after_seconds: 30 })));
  await ctx.loadReport();
  assert.match(textOf(els.reportContent), /Slow down/);
});
test('UI: valid "not_ready" is the honest empty state, not an error', async () => {
  const { ctx, els } = loadUi(fetchOf(resp(200, { status: 'not_ready', message: 'No observations yet.' })));
  await ctx.loadReport();
  const t = textOf(els.reportContent); assert.match(t, /No observations yet/); assert.ok(!/went wrong/.test(t));
});
test('UI: insufficient-data report says so and shows no experiment card', async () => {
  const rep = { status: 'ready', report_state: 'insufficient_data', coverage: { days: 2 }, sections: [{ kind: 'insufficient_evidence', title: 'Not enough history to compare yet.', body: 'Missing: ...' }], data_quality_warnings: [], experiment: null, engine: { state: 'not_run' }, disclaimer: 'd' };
  const { ctx, els } = loadUi(fetchOf(resp(200, rep)));
  await ctx.loadReport();
  const t = textOf(els.reportContent);
  assert.match(t, /NOT ENOUGH DATA YET/); assert.match(t, /INSUFFICIENT EVIDENCE/); assert.ok(!/AN OBSERVATION TO TRY/.test(t));
  assert.match(t, /research engine has not run/);
});
test('UI: timeline failure is a failure card; valid empty timeline is the empty message', async () => {
  const bad = loadUi(fetchOf(resp(500, {}))); await bad.ctx.loadTimeline();
  assert.match(textOf(bad.els.timeline), /Something went wrong/); assert.ok(!/No observations yet/.test(textOf(bad.els.timeline)));
  const empty = loadUi(fetchOf(resp(200, []))); await empty.ctx.loadTimeline();
  assert.match(textOf(empty.els.timeline), /No observations yet/);
});
test('UI: a failed refresh keeps previously loaded timeline rows and adds a notice', async () => {
  let ok = true;
  const f = async () => (ok ? resp(200, [{ kind: 'energy', value: 6, recorded_at: '2026-10-01T08:00:00Z' }]) : resp(500, {}));
  const { ctx, els } = loadUi(f);
  await ctx.loadTimeline(); ok = false; await ctx.loadTimeline();
  const t = textOf(els.timeline); assert.match(t, /energy/); assert.match(t, /Something went wrong/);
});
test('UI: 401 clears the session instead of showing a fake empty state', async () => {
  const { ctx, els } = loadUi(fetchOf(resp(401, {})));
  await ctx.loadReport();
  assert.equal(els.account.textContent, 'Sign in'); assert.match(els.authmsg.textContent, /expired/);
});
