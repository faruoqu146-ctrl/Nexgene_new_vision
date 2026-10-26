/* NexGene API request-state helper.
 *
 * Every call resolves (never rejects) to a result whose `state` is one of:
 *   ready | empty | unauthorized | forbidden | rate_limited | failed | timed_out
 * An API failure is therefore always distinguishable from a valid empty result.
 * Only server-supplied `code` strings and fixed messages are exposed; raw bodies, stack traces and
 * SQL text from error responses are never surfaced to the user.
 */
(function (root) {
  'use strict';
  var DEFAULT_TIMEOUT_MS = 15000;

  function stateForStatus(status) {
    if (status === 401) return 'unauthorized';
    if (status === 403) return 'forbidden';
    if (status === 429) return 'rate_limited';
    if (status === 408 || status === 504) return 'timed_out';
    return 'failed';
  }

  function retryableFor(state, status) {
    // GET requests are safe to repeat; 401/403 will not succeed by retrying.
    return state === 'rate_limited' || state === 'timed_out' || (state === 'failed' && (status === 0 || status >= 500));
  }

  async function apiRequest(url, opts) {
    opts = opts || {};
    var fetchImpl = opts.fetchImpl || root.fetch.bind(root);
    var timeoutMs = opts.timeoutMs || DEFAULT_TIMEOUT_MS;
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timedOut = false;
    var timer = setTimeout(function () { timedOut = true; if (ctrl) ctrl.abort(); }, timeoutMs);
    var started = Date.now();
    function fail(state, status, extra) {
      return Object.assign({ state: state, status: status, retryable: retryableFor(state, status), requestId: null, durationMs: Date.now() - started }, extra || {});
    }
    try {
      var res;
      try {
        res = await fetchImpl(url, ctrl ? { signal: ctrl.signal } : undefined);
      } catch (e) {
        return timedOut || (e && e.name === 'AbortError')
          ? fail('timed_out', 0, { category: 'timeout' })
          : fail('failed', 0, { category: 'network' });
      }
      var requestId = (res.headers && res.headers.get && res.headers.get('X-Request-ID')) || null;
      if (!res.ok) {
        var code = null, retryAfter = null;
        try {
          var errBody = await res.json();
          if (errBody && typeof errBody.code === 'string' && errBody.code.length <= 64) code = errBody.code;
          if (errBody && typeof errBody.retry_after_seconds === 'number') retryAfter = errBody.retry_after_seconds;
        } catch (e) { /* error body unreadable: status alone is enough */ }
        var st = stateForStatus(res.status);
        return fail(st, res.status, { requestId: requestId, code: code, retryAfter: retryAfter, category: 'http' });
      }
      var data;
      try {
        data = await res.json();
      } catch (e) {
        return timedOut ? fail('timed_out', res.status, { requestId: requestId, category: 'timeout' })
                        : fail('failed', res.status, { requestId: requestId, category: 'malformed_response' });
      }
      if (opts.validate && !opts.validate(data)) {
        return fail('failed', res.status, { requestId: requestId, category: 'malformed_response' });
      }
      var empty = opts.isEmpty ? !!opts.isEmpty(data) : false;
      return { state: empty ? 'empty' : 'ready', status: res.status, data: data, requestId: requestId, retryable: false, durationMs: Date.now() - started };
    } finally {
      clearTimeout(timer);
    }
  }

  var MESSAGES = {
    unauthorized: ['Please sign in again', 'Your session has ended.'],
    forbidden: ['Not available', 'This account is not allowed to view this.'],
    rate_limited: ['Slow down a moment', 'Too many requests. Please try again shortly.'],
    timed_out: ['This took too long', 'The server did not answer in time. Your data is safe.'],
    failed: ['Something went wrong', 'We could not load this. This is not an empty result. Please try again.']
  };

  function messageFor(result) {
    var m = MESSAGES[result.state] || MESSAGES.failed;
    var body = m[1];
    if (result.state === 'rate_limited' && typeof result.retryAfter === 'number') body += ' (about ' + result.retryAfter + 's)';
    if (result.category === 'malformed_response') body = 'The server sent a response we could not read. This is not an empty result.';
    if (result.category === 'network') body = 'You appear to be offline. Your data is safe.';
    return { title: m[0], body: body };
  }

  var api = { apiRequest: apiRequest, messageFor: messageFor, stateForStatus: stateForStatus };
  root.NexGeneApi = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
