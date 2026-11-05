/* NexGene progressive-intelligence renderer.
 *
 * Renders ONLY what the API returned from:
 *   POST /api/v1/checkins/{morning|evening}   (response.feedback, the same payload as the endpoint below)
 *   GET  /api/v1/intelligence/progressive     (today snapshot, level availability, signals, next observations)
 *   GET  /api/v1/patterns                     (daily means for the chart)
 *   GET  /api/v1/reports/weekly               (additive `layout` sections)
 *
 * Rules enforced here (and by mobile/tests/progressive-view.test.js):
 *   - Text is set with textContent only; server strings are never parsed as HTML.
 *   - Loading, API failure, "nothing recorded yet" and "not enough history for this comparison" are four
 *     different screens. A failure is never drawn as an empty page, and an empty page never as a failure.
 *   - No number, trend or sentence about the user's data is produced here. Wording comes from the server.
 *   - A missing value is drawn as a gap, never as zero.
 *   - Locked levels say what is required and how far along the user is; they never hide the rest of the screen.
 */
(function (root) {
  'use strict';

  var LEVEL_LABEL = { 1: 'OBSERVATION', 2: 'EARLY PATTERN', 3: 'EXPLORATORY ASSOCIATION', 4: 'PERSONAL BASELINE' };
  var LEVEL_KEYS = [['observations', 'Observations'], ['preliminary_patterns', 'Early patterns'], ['associations', 'Associations'], ['baseline', 'Baseline']];
  var TYPE_LABEL = {
    descriptive_summary: 'WHAT YOU RECORDED', recorded_observation: 'RECORDED', hypothesis: 'WEAK SIGNAL', candidate_association: 'EXPLORATORY ASSOCIATION',
    validated_finding: 'HELD UP ON NEW DAYS', insufficient_evidence: 'NOT ENOUGH YET'
  };

  function el(doc, tag, cls, text) {
    var n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function isObj(x) { return x !== null && typeof x === 'object'; }

  // ---- response validation (a malformed body is a FAILURE, never an empty state) ----
  function validate(d) {
    return isObj(d) && d.schema_version === 'nexgene.progressive/1' && isObj(d.today) && Array.isArray(d.today.values) &&
      isObj(d.levels) && isObj(d.signals) && Array.isArray(d.signals.signals) && Array.isArray(d.next_observations);
  }
  function validateReport(d) { return isObj(d) && Array.isArray(d.layout) && isObj(d.coverage); }
  function validatePatterns(d) { return isObj(d) && Array.isArray(d.series) && isObj(d.averages); }

  // ---- loading ----
  function renderLoading(doc, box, label) {
    clear(box);
    var s = el(doc, 'div', 'skeleton');
    s.setAttribute('aria-busy', 'true');
    s.setAttribute('role', 'status');
    s.append(el(doc, 'i'), el(doc, 'i'), el(doc, 'span', 'srOnly', label || 'Loading'));
    box.appendChild(s);
  }

  // ---- Today ----
  function renderProgress(doc, countEl, barEl, today, detailEl) {
    var n = today.check_ins_complete || 0;
    var m = today.periods && today.periods.morning ? today.periods.morning.status : 'missing';
    var e = today.periods && today.periods.evening ? today.periods.evening.status : 'missing';
    var word = { complete: 'done', partial: 'started', missing: 'open' };
    countEl.textContent = n + ' / 2 check-ins';
    if (detailEl) detailEl.textContent = 'Morning ' + word[m] + ' · Evening ' + word[e];
    barEl.style.width = (Math.min(n, 2) * 50 + ((m === 'partial' ? 1 : 0) + (e === 'partial' ? 1 : 0)) * 15) + '%';
  }

  function renderSnapshot(doc, box, today, handlers) {
    clear(box);
    if (!today.values.length) {
      var empty = el(doc, 'div', 'empty');
      empty.append(el(doc, 'b', null, 'Nothing recorded yet today.'), el(doc, 'span', null, 'One short check-in is enough: your answers appear here the moment you save.'));
      box.appendChild(empty);
      return;
    }
    today.values.forEach(function (v) {
      var m = el(doc, 'div', 'metric');
      m.append(el(doc, 'small', null, String(v.label).toUpperCase()), el(doc, 'b', null, v.display));
      if (v.n_readings > 1) m.appendChild(el(doc, 'span', 'metricNote', v.n_readings + ' readings today'));
      box.appendChild(m);
    });
    var pending = [];
    ['morning', 'evening'].forEach(function (p) {
      var st = today.periods[p];
      if (st && st.status === 'partial' && st.missing_core.length) pending.push(p + ': ' + st.missing_core.join(', ').replace(/_/g, ' ') + ' not recorded');
    });
    if (pending.length) box.appendChild(el(doc, 'div', 'empty slim', 'Incomplete: ' + pending.join(' · ')));
    if (today.skipped && today.skipped.length) {
      box.appendChild(el(doc, 'div', 'empty slim', 'Skipped today (not counted as recorded): ' + today.skipped.map(function (s) { return s.label; }).join(', ')));
    }
  }

  function renderInterpretation(doc, box, today) {
    clear(box);
    var list = today.interpretation || [];
    if (!list.length) { box.textContent = 'Your record is taking shape.'; return; }
    list.slice(0, 3).forEach(function (i) { box.appendChild(el(doc, 'p', null, i.text)); });
  }

  function renderLevels(doc, box, data) {
    clear(box);
    var strip = el(doc, 'div', 'levelStrip');
    LEVEL_KEYS.forEach(function (pair, idx) {
      var lv = data.levels[pair[0]];
      if (!lv) return;
      var status = lv.status || 'locked';
      var chip = el(doc, 'div', 'levelChip ' + status);
      chip.append(el(doc, 'small', null, 'LEVEL ' + (idx + 1)), el(doc, 'b', null, pair[1]),
        el(doc, 'span', null, status === 'available' ? 'available' : status === 'collecting' ? 'collecting data' : 'building'));
      strip.appendChild(chip);
    });
    box.appendChild(strip);
    // say, in words, what the next locked level needs (never hide it behind a generic "not enough data")
    var order = ['preliminary_patterns', 'baseline', 'associations'];
    for (var i = 0; i < order.length; i++) {
      var lv = data.levels[order[i]];
      if (lv && lv.status !== 'available') {
        box.appendChild(el(doc, 'p', 'levelNote', 'Next: ' + lv.label + '. ' + lv.requires));
        break;
      }
    }
  }

  function renderSignals(doc, box, signals, handlers) {
    clear(box);
    (signals.signals || []).forEach(function (sig, i) {
      var card = el(doc, 'div', 'signal');
      var tag = sig.level ? (LEVEL_LABEL[sig.level] || 'SIGNAL') : 'NEXGENE SIGNAL';
      card.append(el(doc, 'small', null, (i === 0 ? '' : '◌ ') + tag), el(doc, 'b', null, sig.title), el(doc, 'span', null, sig.body));
      var act = { check_in: ['CHECK IN', handlers.checkIn], patterns: ['SEE PATTERNS', handlers.patterns], report: ['SEE REPORT', handlers.report], research: ['SEE RESEARCH', handlers.research] }[sig.action];
      if (act && act[1]) { var b = el(doc, 'button', null, act[0]); b.onclick = act[1]; card.appendChild(b); }
      box.appendChild(card);
    });
    if (!box.firstChild) box.appendChild(el(doc, 'div', 'empty', 'The Raven is watching quietly.'));
  }

  function renderNext(doc, box, items, handlers) {
    clear(box);
    if (!items.length) { box.appendChild(el(doc, 'div', 'empty slim', 'Nothing else is needed right now.')); return; }
    items.forEach(function (it) {
      var c = el(doc, 'div', 'signal slim');
      c.appendChild(el(doc, 'span', null, it.text));
      if (it.action === 'check_in' && it.period && handlers.checkIn) {
        var b = el(doc, 'button', null, it.period === 'morning' ? 'MORNING' : 'EVENING');
        b.onclick = function () { handlers.checkIn(it.period); };
        c.appendChild(b);
      }
      box.appendChild(c);
    });
  }

  // ---- check-in sheet states ----
  function renderSaving(doc, box) {
    clear(box);
    var s = el(doc, 'div', 'sheetState saving');
    s.setAttribute('role', 'status');
    s.append(el(doc, 'b', null, 'Saving…'), el(doc, 'span', null, 'Your answers are being stored privately.'));
    box.appendChild(s);
  }

  function renderSaved(doc, box, result) {
    clear(box);
    var s = el(doc, 'div', 'sheetState saved');
    s.setAttribute('role', 'status');
    var n = result.saved || 0;
    s.append(el(doc, 'div', 'k', 'saved'), el(doc, 'h3', null, n ? 'Saved. Here is what NexGene sees so far.' : 'Nothing new to save.'));
    if (result.skipped_duplicates) s.appendChild(el(doc, 'p', 'levelNote', result.skipped_duplicates + ' duplicate answer(s) were already on record and not added again.'));
    var fb = result.feedback;
    if (result.feedback_status === 'unavailable' || !fb) {
      // The save succeeded. Only the instant read-out is missing, and we say so rather than pretending nothing happened.
      s.appendChild(el(doc, 'p', null, 'Your check-in is saved. The instant read-out could not be built this time; it will appear on Today.'));
    } else {
      (fb.today.interpretation || []).slice(0, 3).forEach(function (i) { s.appendChild(el(doc, 'p', null, i.text)); });
      var avail = (fb.available_levels || []).length;
      s.appendChild(el(doc, 'p', 'levelNote', avail > 1 ? 'More is unlocked as your record grows. See Patterns and Report.' : 'This is an observation, not a trend. Patterns need at least two days with the same measurement.'));
    }
    box.appendChild(s);
  }

  function saveErrorMessage(res) {
    var st = res && res.state;
    if (st === 'timed_out' || (st === 'failed' && (res.status === 0 || res.status >= 500))) {
      return { title: 'We could not confirm the save', body: 'Check Today to see whether it went through before trying again, so nothing is recorded twice.', canRetry: true };
    }
    if (st === 'rate_limited') return { title: 'Slow down a moment', body: 'Too many requests. Your answers are still here; try again shortly.', canRetry: true };
    if (st === 'forbidden') return { title: 'Your session needs refreshing', body: 'Sign in again, then repeat this check-in.', canRetry: false };
    if (res && res.status === 422) return { title: 'One answer could not be stored', body: 'Nothing was saved. Close this check-in and try again.' + (res.requestId ? ' Ref ' + res.requestId : ''), canRetry: false };
    return { title: 'Could not save this check-in', body: 'Your answers are still here. Nothing was saved.' + (res && res.requestId ? ' Ref ' + res.requestId : ''), canRetry: true };
  }

  function renderSaveError(doc, box, res, handlers) {
    clear(box);
    var m = saveErrorMessage(res);
    var s = el(doc, 'div', 'sheetState error');
    s.setAttribute('role', 'alert');
    s.append(el(doc, 'b', null, m.title), el(doc, 'span', null, m.body));
    var row = el(doc, 'div', 'aiRow');
    if (m.canRetry && handlers.retry) { var r = el(doc, 'button', null, 'TRY AGAIN'); r.onclick = handlers.retry; row.appendChild(r); }
    if (handlers.check) { var c = el(doc, 'button', 'ghost', 'CHECK TODAY'); c.onclick = handlers.check; row.appendChild(c); }
    s.appendChild(row);
    box.appendChild(s);
  }

  // ---- Patterns ----
  function renderPatterns(doc, cardsBox, chartBox, noteBox, patterns, progressive) {
    var labels = [['sleep_duration', 'Sleep', 'h'], ['sleep_quality', 'Sleep quality', '/10'], ['energy', 'Energy', '/10'], ['mood', 'Mood', '/10'], ['stress', 'Stress', '/10'], ['focus', 'Focus', '/10']];
    clear(cardsBox);
    labels.forEach(function (t) {
      var v = patterns.averages[t[0]];
      if (v === undefined) return;
      var days = patterns.per_kind_days && patterns.per_kind_days[t[0]];
      var p = el(doc, 'div', 'pattern');
      p.append(el(doc, 'small', null, t[1]), el(doc, 'b', null, v + t[2]), el(doc, 'span', null, days ? 'average over ' + days + (days === 1 ? ' day' : ' days') : 'average'));
      cardsBox.appendChild(p);
    });
    if (!cardsBox.firstChild) {
      var e = el(doc, 'div', 'empty');
      e.append(el(doc, 'b', null, 'Nothing to average yet.'), el(doc, 'span', null, 'Your first check-in creates the first figures here, even before there is a pattern.'));
      cardsBox.appendChild(e);
    }
    clear(chartBox);
    var series = patterns.series.slice(-14);
    series.forEach(function (pt) {
      var day = el(doc, 'div', 'day'), bars = el(doc, 'div', 'bars');
      [['sleep_duration', 10], ['focus', 10]].forEach(function (k) {
        var v = pt[k[0]], i = el(doc, 'i', v === undefined ? 'gap' : '');
        if (v !== undefined) i.style.height = Math.max(2, Math.min(100, v / k[1] * 100)) + '%';
        if (v !== undefined) i.setAttribute('title', k[0].replace('_', ' ') + ' ' + v);
        bars.appendChild(i);
      });
      day.append(bars, el(doc, 'small', null, String(pt.date).slice(5)));
      chartBox.appendChild(day);
    });
    if (!chartBox.firstChild) chartBox.appendChild(el(doc, 'div', 'empty', 'No chart yet. Your first check-in draws the first bar.'));
    clear(noteBox);
    var n = patterns.days_with_data;
    if (n !== undefined) {
      noteBox.appendChild(el(doc, 'p', 'levelNote', n + (n === 1 ? ' day' : ' days') + ' of data shown. ' + (n < 2 ? 'A single day is a starting point, not a pattern.' : 'These are descriptive daily averages, not a trend test.')));
    }
    if (progressive) {
      var items = progressive.levels.preliminary_patterns.items || [];
      items.slice(0, 4).forEach(function (it) { noteBox.appendChild(itemCard(doc, it)); });
      if (!items.length) noteBox.appendChild(el(doc, 'div', 'empty slim', 'Early patterns: ' + progressive.levels.preliminary_patterns.requires));
    }
  }

  // ---- Weekly report ----
  function itemCard(doc, it) {
    var card = el(doc, 'article', 'reportCard');
    card.append(el(doc, 'small', null, TYPE_LABEL[it.type] || String(it.type || 'note').replace(/_/g, ' ').toUpperCase()), el(doc, 'h3', null, it.title || it.text || ''), el(doc, 'p', null, it.body || it.text || ''));
    var bits = [];
    if (it.sample && it.sample.days) bits.push('Based on ' + it.sample.days + (it.sample.days === 1 ? ' day' : ' days'));
    if (it.n_week_days !== undefined && it.n_baseline_days !== undefined) bits.push(it.n_week_days + ' recent days vs ' + it.n_baseline_days + ' baseline days');
    if (bits.length) card.appendChild(el(doc, 'small', 'sampleNote', bits.join(' · ')));
    if (Array.isArray(it.limitations) && it.limitations.length) card.appendChild(el(doc, 'small', 'sampleNote', it.limitations[0]));
    return card;
  }

  function sectionNode(doc, sec) {
    var wrap = el(doc, 'section', 'rSection ' + sec.status);
    var head = el(doc, 'div', 'rHead');
    head.append(el(doc, 'h2', null, sec.title), el(doc, 'p', null, sec.summary || ''));
    if (sec.collapsible) {
      var d = el(doc, 'details', 'rDetails');
      var sum = el(doc, 'summary', null, sec.details_title || 'Details');
      d.appendChild(sum);
      if (!sec.collapsed) d.setAttribute('open', '');
      wrap.appendChild(head);
      (sec.warnings || []).forEach(function (w) { d.appendChild(el(doc, 'p', 'reportNote', w.message)); });
      (sec.details || []).forEach(function (x) { var c = el(doc, 'div', 'detailRow'); c.append(el(doc, 'b', null, x.title), el(doc, 'span', null, x.body)); d.appendChild(c); });
      (sec.limitations || []).forEach(function (l) { d.appendChild(el(doc, 'p', 'reportNote', l)); });
      wrap.appendChild(d);
      return wrap;
    }
    wrap.appendChild(head);
    if (sec.id === 'recorded_observations' && (sec.items || []).length) {
      // one compact card of rows: a one-day report must not become a twelve-card scroll
      var card = el(doc, 'article', 'reportCard recordedList');
      sec.items.forEach(function (it) { var row = el(doc, 'div', 'detailRow'); row.append(el(doc, 'b', null, it.title), el(doc, 'span', null, it.body)); card.appendChild(row); });
      wrap.appendChild(card);
    } else {
      (sec.items || []).forEach(function (it) { wrap.appendChild(itemCard(doc, it)); });
    }
    if (sec.not_recorded && sec.not_recorded.length) wrap.appendChild(el(doc, 'p', 'reportNote', 'Not recorded this week: ' + sec.not_recorded.map(function (x) { return x.label; }).join(', ') + '.'));
    if (sec.pair_progress && sec.pair_progress.length && !(sec.items || []).some(function (i) { return i.evidence && i.evidence.source === 'research_engine'; })) {
      sec.pair_progress.forEach(function (pr) { wrap.appendChild(el(doc, 'p', 'reportNote', pr.label + ': ' + pr.paired_days + ' of ' + pr.needed_to_test + ' paired days needed before an association can be tested.')); });
    }
    if (sec.comparison_period && sec.status === 'ready') {
      wrap.appendChild(el(doc, 'p', 'reportNote', 'Compared period: ' + sec.comparison_period.recent[0] + ' to ' + sec.comparison_period.recent[1] + ' against ' + sec.comparison_period.baseline[0] + ' to ' + sec.comparison_period.baseline[1] + '.'));
    }
    return wrap;
  }

  function renderReportLayout(doc, box, report) {
    clear(box);
    var overview = report.layout[0] || {};
    var hero = el(doc, 'div', 'reportHero');
    var eyebrow = (report.coverage.days || 0) + ' OF 7 DAYS RECORDED';
    hero.append(el(doc, 'div', 'eyebrow', eyebrow), el(doc, 'h2', null, report.title || 'Your week with NexGene'), el(doc, 'p', null, overview.summary || report.subtitle || ''));
    box.appendChild(hero);
    report.layout.slice(1).forEach(function (sec) {
      // next-observation items have `text`, not title/body: adapt without inventing content
      if (sec.id === 'next_observations') {
        var w = el(doc, 'section', 'rSection ' + sec.status), h = el(doc, 'div', 'rHead');
        h.append(el(doc, 'h2', null, sec.title), el(doc, 'p', null, sec.summary || ''));
        w.appendChild(h);
        (sec.items || []).forEach(function (it) { var c = el(doc, 'article', 'reportCard'); c.append(el(doc, 'small', null, 'NEXT OBSERVATION'), el(doc, 'p', null, it.text)); w.appendChild(c); });
        box.appendChild(w);
        return;
      }
      box.appendChild(sectionNode(doc, sec));
    });
  }

  var api = { validate: validate, validateReport: validateReport, validatePatterns: validatePatterns, renderLoading: renderLoading, renderProgress: renderProgress,
              renderSnapshot: renderSnapshot, renderInterpretation: renderInterpretation, renderLevels: renderLevels, renderSignals: renderSignals,
              renderNext: renderNext, renderSaving: renderSaving, renderSaved: renderSaved, renderSaveError: renderSaveError, saveErrorMessage: saveErrorMessage,
              renderPatterns: renderPatterns, renderReportLayout: renderReportLayout };
  root.NexGeneProgressive = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
