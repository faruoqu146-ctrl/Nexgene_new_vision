/* NexGene Research screen renderer.
 *
 * Renders ONLY what the research engine persisted and the API returned:
 *   GET /api/v1/intelligence/engine/status    (state, latest run, last completed summary, hypotheses)
 *   GET /api/v1/intelligence/audit/{id}       (gates, tests, provenance for one hypothesis; on demand)
 *   GET /api/v1/intelligence/research/manifest (hash chain across completed runs; on demand)
 *
 * Rules enforced here (and by mobile/tests/research-view.test.js):
 *   - Text is set with textContent only; server strings are never parsed as HTML.
 *   - A missing value is shown as "not reported", never as zero and never silently dropped.
 *   - "never ran", "failed", "interrupted", "stale" and "ran, nothing qualified" are different screens.
 *   - No number, grade or sentence is generated here. Wording comes from the engine's own brief.
 *   - Retrieved literature is labelled as context and is never presented as support.
 */
(function (root) {
  'use strict';

  var NOT_REPORTED = 'not reported';

  var STATE_COPY = {
    not_run: ['No research run yet', 'Nothing has been analyzed, so there are no findings. This is not a negative result.'],
    running: ['A research run is in progress', 'Any results below come from an earlier completed run.'],
    interrupted: ['The last run was interrupted', 'It produced no results. Any results below come from an earlier completed run.'],
    failed: ['The last run failed', 'This is a failure, not an absence of findings. Any results below come from an earlier completed run.'],
    stale: ['These results may be out of date', 'Something changed since this run (see reasons). Run the analysis again to refresh.'],
    current: ['Up to date', 'This report is the latest completed run and nothing newer has been recorded since.']
  };
  var STALE_REASON = {
    model_version_changed: 'the analysis version changed',
    older_than_freshness_window: 'the run is older than the freshness window',
    new_observations_since_run: 'new observations were recorded after the run'
  };

  function el(doc, tag, cls, text) {
    var n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }

  function isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }

  /** Compact, honest formatter. null/undefined -> "not reported". Never fabricates a value. */
  function fmt(v, depth) {
    depth = depth || 0;
    if (v === null || v === undefined || v === '') return NOT_REPORTED;
    if (typeof v === 'boolean') return v ? 'yes' : 'no';
    if (typeof v === 'number') return Number.isFinite(v) ? String(Math.abs(v) >= 100 ? Math.round(v * 10) / 10 : Math.round(v * 1000) / 1000) : NOT_REPORTED;
    if (typeof v === 'string') return v;
    if (Array.isArray(v)) {
      if (!v.length) return 'none';
      var items = v.slice(0, 8).map(function (x) { return fmt(x, depth + 1); });
      return items.join(', ') + (v.length > 8 ? ' … (+' + (v.length - 8) + ' more)' : '');
    }
    if (isObj(v)) {
      var keys = Object.keys(v);
      if (!keys.length) return 'none';
      if (depth >= 2) return keys.length + ' fields';
      return keys.slice(0, 12).map(function (k) { return k.replace(/_/g, ' ') + ': ' + fmt(v[k], depth + 1); }).join('; ');
    }
    return String(v);
  }

  function when(iso) {
    if (!iso) return NOT_REPORTED;
    var d = new Date(iso);
    return isNaN(d.getTime()) ? NOT_REPORTED : d.toLocaleString();
  }

  function kv(doc, rows) {
    var box = el(doc, 'div', 'rsKv');
    rows.forEach(function (r) {
      var row = el(doc, 'div', 'rsRow');
      row.append(el(doc, 'small', null, r[0]), el(doc, 'span', null, r[1]));
      box.appendChild(row);
    });
    return box;
  }

  function card(doc, letter, title, cls) {
    var c = el(doc, 'article', 'reportCard rsCard' + (cls ? ' ' + cls : ''));
    c.append(el(doc, 'small', null, letter ? 'SECTION ' + letter : ''), el(doc, 'h3', null, title));
    return c;
  }

  function unavailable(doc, why) { return el(doc, 'p', 'reportNote rsUnavailable', 'Not available: ' + why); }

  function list(doc, items) {
    var ul = el(doc, 'ul', 'rsList');
    items.forEach(function (t) { ul.appendChild(el(doc, 'li', null, t)); });
    return ul;
  }

  /** `state` is a dict {state, stale_reasons, failure_category,…} from the server. Accept a bare string too. */
  function stateOf(status) {
    var s = status && status.state;
    if (typeof s === 'string') return { state: s, stale_reasons: [] };
    if (isObj(s) && typeof s.state === 'string') return s;
    return { state: null, stale_reasons: [] };
  }

  function validateStatus(d) {
    return isObj(d) && 'hypothesis_counts' in d && 'evidence_ladder' in d && (stateOf(d).state in STATE_COPY);
  }

  function candidateKey(h) { return h.exposure + '->' + h.outcome + '@' + h.lag; }

  function joinHypothesis(finding, hypotheses) {
    var list_ = hypotheses || [];
    for (var i = 0; i < list_.length; i++) if (candidateKey(list_[i]) === finding.id) return list_[i];
    return null;
  }

  // ---------------------------------------------------------------- banner
  function renderBanner(doc, status, h) {
    var st = stateOf(status), copy = STATE_COPY[st.state];
    var run = status.latest_run, done = status.last_completed_run, summary = status.last_run;
    var box = el(doc, 'div', 'reportHero rsBanner rsState-' + st.state);
    box.append(el(doc, 'div', 'eyebrow', 'RESEARCH ENGINE'), el(doc, 'h2', null, copy[0]), el(doc, 'p', null, copy[1]));
    if (st.state === 'stale') {
      var why = (st.stale_reasons || []).map(function (r) { return STALE_REASON[r] || r; });
      box.appendChild(el(doc, 'p', 'reportNote', 'Reason: ' + (why.length ? why.join('; ') : NOT_REPORTED) + '.'));
    }
    if (st.state === 'failed') box.appendChild(el(doc, 'p', 'reportNote', 'Failure category: ' + fmt(st.failure_category) + '. Your data was not changed.'));
    var lines = [];
    if (run) lines.push('Latest attempt: run ' + run.id + ', ' + run.status + ', ' + when(run.created_at));
    if (summary) {
      if (done) lines.push('Showing completed run ' + done.id + ' from ' + when(done.created_at));
      else lines.push('Showing the latest completed run (its identifier was not reported by the server)');
    }
    lines.forEach(function (t) { box.appendChild(el(doc, 'p', 'reportNote', t)); });
    var b = el(doc, 'button', 'rsRun', st.state === 'running' ? 'RUN IN PROGRESS' : (summary ? 'RUN ANALYSIS AGAIN' : 'RUN ANALYSIS'));
    if (st.state === 'running') b.disabled = true;
    b.onclick = function () { if (h && h.onRun) h.onRun(b); };
    box.appendChild(b);
    box.appendChild(el(doc, 'p', 'reportNote rsRunMsg', ''));
    return box;
  }

  // ---------------------------------------------------------------- A
  function renderSummary(doc, status) {
    var c = card(doc, 'A', 'Research-run summary'), s = status.last_run, done = status.last_completed_run;
    var q = s.quality || {};
    c.appendChild(kv(doc, [
      ['Run identifier', done ? String(done.id) : NOT_REPORTED],
      ['Generated', done ? when(done.created_at) : NOT_REPORTED],
      ['Engine', fmt(s.engine)], ['Analysis version', fmt(s.model_version)],
      ['Analysis window', s.window_days === undefined || s.window_days === null ? NOT_REPORTED : s.window_days + ' days'],
      ['Observations analyzed', fmt(s.observation_count)], ['Days with data', fmt(s.active_days)], ['Weeks with data', fmt(s.active_weeks)],
      ['Variables analyzed', fmt(s.numeric_kinds)], ['Data-quality score', fmt(q.score)],
      ['Quality components', fmt(q.components)], ['Execution status', done ? 'completed' : NOT_REPORTED]
    ]));
    var inel = q.ineligible_variables;
    if (isObj(inel) && Object.keys(inel).length) {
      c.appendChild(el(doc, 'p', 'reportNote', 'Variables excluded from analysis, with reasons:'));
      c.appendChild(list(doc, Object.keys(inel).map(function (k) { return k.replace(/_/g, ' ') + ': ' + fmt(inel[k]); })));
    }
    (q.warnings || []).forEach(function (w) { c.appendChild(el(doc, 'p', 'reportNote', 'Data-quality warning: ' + fmt(w))); });
    return c;
  }

  // ---------------------------------------------------------------- B
  function renderFinding(doc, f, hyp, h) {
    var c = el(doc, 'div', 'rsFinding');
    c.append(el(doc, 'small', null, (f.tier || 'ERL-?') + ' · ' + fmt(f.tier_label) + ' · status ' + fmt(f.status)), el(doc, 'h4', null, f.headline));
    c.appendChild(el(doc, 'p', null, f.effect));
    c.appendChild(el(doc, 'p', 'reportNote', f.evidence));
    if (hyp) {
      var u = hyp.uncertainty || {};
      c.appendChild(kv(doc, [
        ['Paired days (n)', fmt(hyp.n_pairs)], ['95% interval for r', fmt(u.ci_95)], ['p-value', fmt(hyp.p_value)],
        ['Family-adjusted q', fmt(hyp.q_value)], ['Last tested', when(hyp.last_tested_at)]
      ]));
    } else {
      c.appendChild(unavailable(doc, 'no stored hypothesis matches this finding, so its numeric diagnostics cannot be shown.'));
    }
    if (f.caveats && f.caveats.length) { c.appendChild(el(doc, 'small', null, 'QUALIFICATIONS')); c.appendChild(list(doc, f.caveats)); }
    if (f.falsifiers && f.falsifiers.length) { c.appendChild(el(doc, 'small', null, 'WHAT WOULD WEAKEN THIS')); c.appendChild(list(doc, f.falsifiers)); }
    if (f.forward_test) c.appendChild(el(doc, 'p', null, f.forward_test));
    if (f.experiment) c.appendChild(el(doc, 'p', null, f.experiment));
    if (f.echo_note) c.appendChild(el(doc, 'p', 'reportNote', f.echo_note + ' Also seen at: ' + fmt(f.also_seen_at) + '.'));
    var detail = el(doc, 'div', 'rsAudit');
    if (hyp) {
      var b = el(doc, 'button', 'rsLink', 'WHY THIS GRADE · DIAGNOSTICS');
      b.onclick = function () { if (h && h.onAudit) h.onAudit(hyp.hypothesis_id, detail, b); };
      c.appendChild(b);
    }
    c.appendChild(detail);
    return c;
  }

  function renderFindings(doc, status, h) {
    var c = card(doc, 'B', 'Principal findings'), s = status.last_run, brief = s.brief;
    if (!isObj(brief)) { c.appendChild(unavailable(doc, 'the completed run did not store a research brief.')); return c; }
    var counts = brief.tier_counts || {};
    var findings = brief.findings || [];
    if (!findings.length) {
      if (brief.status === 'starting') c.appendChild(el(doc, 'p', null, 'No relationships have been tested yet: there is not enough data. This is missing data, not a negative result.'));
      else c.appendChild(el(doc, 'p', null, 'The analysis ran and tested relationships, but none reached the reporting bar (evidence level 1 or higher). This is a completed run with no qualifying findings, not a failure.'));
      c.appendChild(kv(doc, [['Candidate relationships tested', fmt(s.candidate_relationships)], ['Evidence levels reached', fmt(counts)]]));
    }
    findings.forEach(function (f) { c.appendChild(renderFinding(doc, f, joinHypothesis(f, status.top_hypotheses), h)); });
    var alerts = brief.baseline_alerts || [];
    if (alerts.length) {
      c.appendChild(el(doc, 'small', null, 'BASELINE CHANGES'));
      alerts.forEach(function (a) { c.appendChild(el(doc, 'p', null, a.message + ' (method: ' + fmt(a.method) + '; since: ' + fmt(a.since) + ')')); });
    }
    return c;
  }

  // ---------------------------------------------------------------- C
  function renderMethod(doc, status) {
    var c = card(doc, 'C', 'Analytical method'), s = status.last_run;
    if (Array.isArray(s.methodology) && s.methodology.length) {
      c.appendChild(el(doc, 'p', 'reportNote', 'Methods the engine applies, as recorded with this run:'));
      c.appendChild(list(doc, s.methodology));
    } else c.appendChild(unavailable(doc, 'the completed run did not store its methodology.'));
    c.appendChild(kv(doc, [['Multiple-testing families (size)', fmt(s.families)], ['Candidates tested', fmt((s.sufficiency || {}).candidates_tested)],
      ['Median effective sample size', fmt((s.sufficiency || {}).median_effective_n)],
      ['Smallest detectable r (primary family, 80% power)', fmt((s.sufficiency || {}).mde_r_80_primary_family)]]));
    return c;
  }

  // ---------------------------------------------------------------- D
  function renderRobustness(doc, status) {
    var c = card(doc, 'D', 'Robustness and uncertainty'), s = status.last_run;
    c.appendChild(kv(doc, [['Evidence levels reached (this run)', fmt(s.evidence_tiers)], ['Hypotheses on file by status', fmt(status.hypothesis_counts)]]));
    var ladder = status.evidence_ladder || {};
    var codes = Object.keys(ladder);
    if (codes.length) { c.appendChild(el(doc, 'small', null, 'WHAT EACH EVIDENCE LEVEL MEANS')); c.appendChild(list(doc, codes.map(function (k) { return k + ' ' + fmt(ladder[k].label) + ': ' + fmt(ladder[k].meaning); }))); }
    c.appendChild(el(doc, 'p', 'reportNote', 'Per-finding robustness checks, gates and sensitivity analyses are in each finding\u2019s diagnostics. Findings that failed a gate show it there.'));
    if (s.epistemic_boundary) c.appendChild(el(doc, 'p', 'reportNote', s.epistemic_boundary));
    if (Array.isArray(s.limitations) && s.limitations.length) { c.appendChild(el(doc, 'small', null, 'LIMITATIONS')); c.appendChild(list(doc, s.limitations)); }
    return c;
  }

  // ---------------------------------------------------------------- E
  function renderEvidence(doc, status) {
    var c = card(doc, 'E', 'Evidence and research context');
    c.appendChild(el(doc, 'p', 'reportNote', 'Retrieved articles are context only. They are not used to compute estimates or to raise an evidence level.'));
    var shown = 0;
    (status.top_hypotheses || []).forEach(function (hy) {
      (hy.evidence || []).filter(function (e) { return e && e.type === 'retrieved_context'; }).forEach(function (e) {
        shown++;
        c.appendChild(el(doc, 'p', null, fmt(e.title) + ' (' + fmt(e.published_year) + ') for ' + hy.exposure.replace(/_/g, ' ') + ' and ' + hy.outcome.replace(/_/g, ' ')
          + ' · appraised: ' + (e.appraised === true ? 'yes' : 'no') + (e.evidence_grade ? ' · grade on import: ' + e.evidence_grade : '')));
        if (e.url) c.appendChild(el(doc, 'small', 'rsUrl', e.url));
      });
    });
    if (!shown) c.appendChild(unavailable(doc, 'no retrieved literature is stored for these hypotheses. No evidence import has matched them.'));
    return c;
  }

  // ---------------------------------------------------------------- F
  function renderNext(doc, status) {
    var c = card(doc, 'F', 'Next steps'), brief = status.last_run.brief || {};
    var ex = brief.next_experiments || [];
    if (ex.length) {
      ex.forEach(function (e) {
        c.appendChild(el(doc, 'p', null, 'Candidate self-experiment: ' + e.exposure.replace(/_/g, ' ') + ' \u2192 ' + e.outcome.replace(/_/g, ' ') + '. ' + fmt(e.why)));
        c.appendChild(kv(doc, [['Days needed', fmt(e.days_needed)], ['Feasible within 8 weeks', fmt(e.feasible_in_8_weeks)], ['Controllability', fmt(e.controllability)]]));
      });
    } else c.appendChild(el(doc, 'p', null, 'No self-experiment can be recommended: one requires an evidence level 2 or higher association on an exposure you can deliberately change.'));
    var pend = status.pending_predictions || [];
    c.appendChild(el(doc, 'small', null, 'FORWARD TESTS WAITING FOR NEW DAYS'));
    if (pend.length) c.appendChild(list(doc, pend.map(function (p) { return 'Prediction ' + p.id + ' for ' + when(p.target_start) + ' to ' + when(p.target_end) + ' (expected ' + fmt(p.expected_direction) + ')'; })));
    else c.appendChild(el(doc, 'p', 'reportNote', 'None pending.'));
    var sf = brief.sufficiency || {};
    c.appendChild(kv(doc, [['Eligible variables', fmt(sf.variables_eligible)], ['More data would resolve', 'see each finding\u2019s data-sufficiency gate']]));
    return c;
  }

  // ---------------------------------------------------------------- G
  function renderAuditCard(doc, status, h) {
    var c = card(doc, 'G', 'Audit and reproducibility'), m = status.last_run.manifest;
    if (!isObj(m)) { c.appendChild(unavailable(doc, 'the completed run did not store a manifest, so it cannot be verified.')); return c; }
    c.appendChild(kv(doc, [['Run hash', fmt(m.run_hash)], ['Input-data hash', fmt(m.input_hash)], ['Configuration hash', fmt(m.config_hash)], ['Random seed', fmt(m.seed)],
      ['Code fingerprint', fmt(m.code_fingerprint)], ['Results hash', fmt(m.results_hash)], ['Previous run hash', fmt(m.prev_run_hash)],
      ['Engine / model version', fmt(m.engine_version) + ' / ' + fmt(m.model_version)]]));
    var hist = el(doc, 'div', 'rsHistory');
    var b = el(doc, 'button', 'rsLink', 'RUN HISTORY AND HASH CHAIN');
    b.onclick = function () { if (h && h.onHistory) h.onHistory(hist, b); };
    c.append(b, hist);
    return c;
  }

  /** Full screen. Nothing is drawn for a section the data cannot support; the section says why instead. */
  function renderResearch(doc, box, status, handlers) {
    while (box.firstChild) box.removeChild(box.firstChild);
    box.appendChild(renderBanner(doc, status, handlers));
    if (!status.last_run) {
      var c = card(doc, '', 'Report unavailable');
      c.appendChild(unavailable(doc, 'no analysis run has completed yet, so there is no run summary, findings, method, robustness, evidence, next steps or audit record to show.'));
      box.appendChild(c);
      return;
    }
    [renderSummary, renderFindings, renderMethod, renderRobustness, renderEvidence, renderNext, renderAuditCard].forEach(function (fn) {
      box.appendChild(fn(doc, status, handlers));
    });
  }

  // ---------------------------------------------------------------- on-demand panels
  function renderAudit(doc, into, audit, runHash) {
    while (into.firstChild) into.removeChild(into.firstChild);
    var hy = audit.hypothesis || {}, an = hy.analysis || {};
    var prov = audit.provenance || {};
    if (runHash && prov.run_hash && prov.run_hash !== runHash) {
      into.appendChild(el(doc, 'p', 'reportNote rsWarn', 'These diagnostics are from a different run than the report above (hash differs). Run the analysis again before relying on them.'));
    }
    into.appendChild(el(doc, 'small', null, 'EVIDENCE GATES'));
    var gates = hy.gates || [];
    if (gates.length) into.appendChild(list(doc, gates.map(function (g) { return (g.passed === true ? 'PASS' : g.passed === false ? 'FAIL' : 'NOT RUN') + ' \u00b7 ' + String(g.id).replace(/_/g, ' ') + ': ' + fmt(g.detail); })));
    else into.appendChild(unavailable(doc, 'no gate table was stored.'));
    var rows = [];
    ['inference', 'effect', 'bayes', 'robustness', 'directional_test', 'sensitivity', 'power', 'missingness'].forEach(function (k) { rows.push([k.replace(/_/g, ' '), fmt(an[k])]); });
    into.appendChild(kv(doc, rows));
    if (an.notes) into.appendChild(el(doc, 'p', 'reportNote', fmt(an.notes)));
    if ((hy.alternatives || []).length) { into.appendChild(el(doc, 'small', null, 'COMPETING EXPLANATIONS')); into.appendChild(list(doc, hy.alternatives)); }
    var tests = audit.tests || [];
    into.appendChild(el(doc, 'small', null, 'TEST HISTORY'));
    if (tests.length) into.appendChild(list(doc, tests.slice(0, 5).map(function (t) { return 'Run ' + t.run_id + ' \u00b7 n ' + fmt(t.sample_size) + ' \u00b7 effect ' + fmt(t.effect_estimate) + ' \u00b7 q ' + fmt(t.q_value) + ' \u00b7 ' + fmt(t.result_status); })));
    else into.appendChild(el(doc, 'p', 'reportNote', 'No stored tests.'));
    into.appendChild(el(doc, 'p', 'reportNote', 'Forward tests: ' + (audit.predictions || []).length + ' \u00b7 Randomized self-experiments: ' + (audit.experiments || []).length));
  }

  function renderHistory(doc, into, resp) {
    while (into.firstChild) into.removeChild(into.firstChild);
    var ms = resp.manifests || [], ch = resp.chain || {};
    into.appendChild(el(doc, 'p', null, ms.length + ' completed run(s) \u00b7 hash chain ' + (ch.ok === true ? 'verified' : ch.ok === false ? 'BROKEN (' + (ch.problems || []).length + ' problem(s))' : NOT_REPORTED)));
    if (ms.length) into.appendChild(list(doc, ms.slice().reverse().map(function (m) { return 'Run ' + m.run_id + ' \u00b7 ' + when(m.created_at) + ' \u00b7 ' + String(m.run_hash || '').slice(0, 12); })));
    if (resp.note) into.appendChild(el(doc, 'p', 'reportNote', resp.note));
  }

  /** Message for a failed/refused run request. Distinguishes busy, cooldown and failure; never reports success. */
  function runMessage(res) {
    if (res.state === 'unauthorized') return 'Please sign in again.';
    if (res.state === 'timed_out') return 'The server did not answer in time. The run may still be in progress; check the status again shortly.';
    if (res.code === 'engine_running') return 'A run is already in progress. Check back shortly.';
    if (res.code === 'engine_cooldown' || res.state === 'rate_limited') return 'A run finished recently.' + (typeof res.retryAfter === 'number' ? ' Try again in about ' + res.retryAfter + ' seconds.' : ' Please wait before running again.');
    if (res.code === 'engine_failed') return 'The run failed. Your data was not changed.' + (res.requestId ? ' Ref ' + res.requestId : '');
    return 'The run could not be started. This is not an empty result.' + (res.requestId ? ' Ref ' + res.requestId : '');
  }

  var api = { renderResearch: renderResearch, renderAudit: renderAudit, renderHistory: renderHistory, runMessage: runMessage,
              validateStatus: validateStatus, stateOf: stateOf, joinHypothesis: joinHypothesis, fmt: fmt, STATE_COPY: STATE_COPY };
  root.NexGeneResearch = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
