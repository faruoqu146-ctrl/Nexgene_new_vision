/* NexGene intelligence shell — wired to real API only */
(() => {
  const API = window.location.origin.replace(/\/$/, "");
  const FOUNDER = "faruoqu146@gmail.com";
  const $ = (id) => document.getElementById(id);
  const state = {
    user: null,
    csrf: "",
    route: "overview",
    authMode: "login",
    checkinPeriod: "morning",
    checkinData: {},
    timeline: [],
    patterns: null,
    signals: null,
    insights: null,
    weekly: null,
    consent: null,
    profile: null,
    health: null,
  };

  const MORNING = [
    { kind: "sleep_duration", label: "Sleep duration", unit: "hours", options: [
      ["Under 5h", 4.5], ["5–6h", 5.5], ["6–7h", 6.5], ["7–8h", 7.5], ["8–9h", 8.5], ["9h+", 9.5],
    ]},
    { kind: "sleep_quality", label: "Sleep quality", unit: "0–10", options: [
      ["Rough", 2], ["Restless", 4], ["Okay", 6], ["Good", 8], ["Deep", 10],
    ]},
    { kind: "energy", label: "Energy on arrival", unit: "0–10", options: [
      ["Drained", 2], ["Low", 4], ["Steady", 6], ["Good", 8], ["Charged", 10],
    ]},
    { kind: "morning_context", label: "Anything unusual", unit: "context", options: [
      ["Nothing unusual", "none"], ["Headache", "headache"], ["Fatigue", "fatigue"], ["Pain", "pain"], ["Skip", "skipped"],
    ]},
  ];
  const EVENING = [
    { kind: "mood", label: "Mood", unit: "0–10", options: [["Low", 2], ["Heavy", 4], ["Mixed", 6], ["Good", 8], ["Great", 10]] },
    { kind: "stress", label: "Stress", unit: "0–10", options: [["Very low", 1], ["Low", 3], ["Moderate", 5], ["High", 7], ["Very high", 9]] },
    { kind: "focus", label: "Focus", unit: "0–10", options: [["Scattered", 2], ["Patchy", 4], ["Okay", 6], ["Strong", 8], ["Locked in", 10]] },
    { kind: "activity_level", label: "Movement", unit: "0–10", options: [["Very little", 2], ["Light", 4], ["Moderate", 6], ["A lot", 8], ["Skip", 0]] },
    { kind: "diet_quality", label: "Eating quality", unit: "0–10", options: [["Chaotic", 2], ["Mostly quick", 4], ["Mixed", 6], ["Mostly balanced", 8], ["Very balanced", 10]] },
    { kind: "caffeine", label: "Caffeine", unit: "servings", options: [["None", 0], ["1", 1], ["2", 2], ["3+", 3]] },
    { kind: "alcohol", label: "Alcohol", unit: "servings", options: [["None", 0], ["1", 1], ["2", 2], ["3+", 3]] },
    { kind: "nicotine", label: "Nicotine", unit: "relative", options: [["None", 0], ["Some", 2], ["Frequent", 5]] },
  ];

  const ARCH = [
    { id: "L0", title: "Consent, identity & governance", purpose: "Controls what may be collected, processed, retained, combined, and used for which purposes.", status: "available", inputs: "User grants, policy version", outputs: "Authorized purpose set", deps: "Account session" },
    { id: "L1", title: "Data acquisition & provenance", purpose: "Sources entering the system with metadata.", status: "available", inputs: "Check-ins, batch imports, optional live context", outputs: "Source records, observation links", deps: "L0 collect purpose" },
    { id: "L2", title: "Canonical longitudinal records", purpose: "Normalized, timestamped observations with event vs ingestion time.", status: "available", inputs: "L1 sources", outputs: "Timeline, coverage metrics", deps: "L1" },
    { id: "L3", title: "Domain intelligence", purpose: "Lifestyle primary; physiological/clinical/genomic according to deployment.", status: "limited", inputs: "L2 domain slices", outputs: "Domain coverage & baselines where implemented", deps: "L2 + domain consent" },
    { id: "L4", title: "Shared research & analysis engine", purpose: "Patterns, reports, optional hypothesis engine.", status: "limited", inputs: "L2–L3", outputs: "Patterns, weekly report, engine status", deps: "Sufficient observations" },
    { id: "L5", title: "Evidence, uncertainty & safety", purpose: "Separates observed, calculated, exploratory; refuses unsupported claims.", status: "limited", inputs: "L4 outputs, literature endpoints if enabled", outputs: "Epistemic labels, limitations", deps: "Honest UI + engine metadata" },
    { id: "L6", title: "User-facing intelligence", purpose: "Summaries and next steps without clinical overclaim.", status: "available", inputs: "L4–L5", outputs: "Overview, signals, reports", deps: "L0–L2" },
  ];

  const MATURITY = [
    { name: "Lifestyle check-ins", status: "available", note: "Morning/evening flows" },
    { name: "Longitudinal timeline", status: "available", note: "Event vs recorded time" },
    { name: "Pattern summaries", status: "available", note: "Descriptive only" },
    { name: "Weekly report", status: "available", note: "Coverage-aware" },
    { name: "Intelligence engine", status: "limited", note: "Depends on deployment config" },
    { name: "Clinical compartment", status: "planned", note: "Isolated; not implied active" },
    { name: "Genomic compartment", status: "planned", note: "Isolated; not implied active" },
    { name: "External literature", status: "limited", note: "If evidence endpoints enabled" },
  ];

  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.remove("hide");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hide"), 3200);
  }

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  async function api(path, opts = {}) {
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    if (opts.csrf) {
      state.csrf = getCookie("nexgene_csrf") || state.csrf;
      if (state.csrf) headers["X-CSRF-Token"] = state.csrf;
    }
    const res = await fetch(API + path, {
      method: opts.method || "GET",
      credentials: "include",
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    let data = null;
    const text = await res.text();
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
    if (!res.ok) {
      const err = new Error((data && (data.detail || data.message)) || res.statusText || "Request failed");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  async function refreshCsrf() {
    await api("/api/v1/auth/csrf");
    state.csrf = getCookie("nexgene_csrf");
  }

  async function ensureSession() {
    try {
      state.user = await api("/api/v1/auth/me");
      await refreshCsrf();
      return true;
    } catch {
      state.user = null;
      return false;
    }
  }

  function setAuthVisible(on) {
    $("view-auth").classList.toggle("hide", !on);
    $("shell").classList.toggle("hide", on);
  }

  function setRoute(name) {
    state.route = name;
    document.querySelectorAll(".route").forEach((el) => el.classList.add("hide"));
    const target = $("route-" + name);
    if (target) target.classList.remove("hide");
    document.querySelectorAll("[data-route]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-route") === name);
    });
    const titles = {
      overview: ["Overview", "Home"],
      checkin: ["Check-in", "Record"],
      data: ["My data", "Longitudinal"],
      patterns: ["Patterns", "Descriptive"],
      research: ["Research", "Reports"],
      map: ["Architecture", "Layers"],
      privacy: ["Privacy", "Permissions"],
      account: ["Account", "Session"],
    };
    const t = titles[name] || [name, ""];
    $("page-title").textContent = t[0];
    $("page-eyebrow").textContent = t[1];
    $("sidebar").classList.remove("open");
    $("main").focus({ preventScroll: true });
    loadRoute(name);
  }

  function statusTag(status) {
    const map = { available: "ok", limited: "warn", planned: "muted", unavailable: "err" };
    return `<span class="tag ${map[status] || "muted"}">${status}</span>`;
  }

  function renderOverview() {
    const tl = state.timeline || [];
    const kinds = new Set(tl.map((r) => r.kind));
    const dates = new Set(tl.map((r) => (r.event_at || r.observed_at || r.recorded_at || "").slice(0, 10)).filter(Boolean));
    $("overview-stats").innerHTML = `
      <div class="stat-card"><div class="label">Observations in view</div><div class="value">${tl.length}</div><div class="hint">API timeline window (max 300)</div></div>
      <div class="stat-card"><div class="label">Distinct kinds</div><div class="value">${kinds.size}</div><div class="hint">Lifestyle variables represented</div></div>
      <div class="stat-card"><div class="label">Calendar days touched</div><div class="value">${dates.size}</div><div class="hint">By event time when present</div></div>
      <div class="stat-card"><div class="label">Epistemic stance</div><div class="value" style="font-size:1rem">Descriptive</div><div class="hint">Not a clinical clearance</div></div>`;

    const actions = [];
    actions.push(`<button type="button" class="btn primary" data-go="checkin">Record a check-in</button>`);
    actions.push(`<button type="button" class="btn" data-go="data">Inspect timeline</button>`);
    actions.push(`<button type="button" class="btn" data-go="map">Open architecture map</button>`);
    $("overview-actions").innerHTML = actions.join("") || `<div class="empty"><b>No actions</b></div>`;
    $("overview-actions").querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => setRoute(b.getAttribute("data-go"))));

    const sig = state.signals;
    if (sig && Array.isArray(sig.signals) && sig.signals.length) {
      $("overview-signals").innerHTML = sig.signals.map((s) =>
        `<div class="panel" style="margin:0"><b>${esc(s.title || "Signal")}</b><p class="muted" style="margin:6px 0 0">${esc(s.body || "")}</p>
        <details class="derive"><summary>How this was framed</summary>
        <dl><dt>Category</dt><dd>Descriptive signal</dd><dt>Status</dt><dd>${esc(sig.status || "unknown")}</dd>
        <dt>Limitation</dt><dd>Not a diagnosis or risk score</dd></dl></details></div>`
      ).join("");
    } else {
      $("overview-signals").innerHTML = `<div class="empty"><b>No signals yet</b><span>More longitudinal coverage produces descriptive signals — not predictions.</span></div>`;
    }

    $("overview-maturity").innerHTML = MATURITY.map((m) =>
      `<div class="maturity-row"><div><b>${esc(m.name)}</b><div class="muted">${esc(m.note)}</div></div>${statusTag(m.status)}</div>`
    ).join("");

    const founder = state.user && state.user.email && state.user.email.toLowerCase() === FOUNDER;
    $("founder-banner").classList.toggle("hide", !founder);
  }

  function renderCheckin() {
    const fields = state.checkinPeriod === "morning" ? MORNING : EVENING;
    $("checkin-form").innerHTML = fields.map((f) => {
      const selected = state.checkinData[f.kind];
      return `<div class="panel" style="margin:0">
        <div class="panel-head"><h2>${esc(f.label)}</h2><span class="tag muted">${esc(f.unit)}</span></div>
        <div class="choice-grid" data-kind="${f.kind}">
          ${f.options.map(([lab, val]) => {
            const sel = selected === val || selected === String(val);
            return `<button type="button" class="choice ${sel ? "selected" : ""}" data-val="${esc(String(val))}"><b>${esc(lab)}</b><span>${esc(String(val))}</span></button>`;
          }).join("")}
        </div>
      </div>`;
    }).join("");
    $("checkin-form").querySelectorAll(".choice").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.parentElement.getAttribute("data-kind");
        let val = btn.getAttribute("data-val");
        if (val !== "none" && val !== "headache" && val !== "fatigue" && val !== "pain" && val !== "skipped") {
          const n = Number(val);
          if (!Number.isNaN(n)) val = n;
        }
        state.checkinData[kind] = val;
        renderCheckin();
      });
    });
  }

  function renderData() {
    const filter = $("data-filter-kind").value;
    const rows = (state.timeline || []).filter((r) => !filter || r.kind === filter);
    const kinds = [...new Set((state.timeline || []).map((r) => r.kind))].sort();
    const sel = $("data-filter-kind");
    const cur = sel.value;
    sel.innerHTML = `<option value="">All kinds</option>` + kinds.map((k) => `<option value="${esc(k)}">${esc(k)}</option>`).join("");
    sel.value = cur;

    if (!rows.length) {
      $("data-timeline").innerHTML = `<div class="empty"><b>No observations in view</b><span>Complete a check-in or import authorized history.</span></div>`;
      return;
    }
    $("data-timeline").innerHTML = rows.map((r) => {
      const event = r.event_at || r.observed_at || r.recorded_at || "";
      const rec = r.recorded_at || "";
      return `<article class="tl-item">
        <time datetime="${esc(event)}">${esc((event || "").slice(0, 16).replace("T", " "))}</time>
        <div>
          <div class="kind">${esc(r.kind)} · <span class="muted">${esc(String(r.value))}</span></div>
          <div class="meta">Event ${esc(event || "—")} · Recorded ${esc(rec || "—")}${r.period ? " · " + esc(r.period) : ""}</div>
        </div>
      </article>`;
    }).join("");
  }

  function renderPatterns() {
    const p = state.patterns;
    if (!p || !p.series || !p.series.length) {
      $("patterns-body").innerHTML = `<div class="empty"><b>Insufficient series for charts</b><span>Patterns require repeated observations across days.</span></div>`;
      return;
    }
    const series = p.series.slice(-30);
    const sleep = series.map((d) => d.sleep_duration).filter((v) => v != null);
    const max = Math.max(10, ...series.flatMap((d) => [d.sleep_duration, d.focus, d.stress, d.energy].filter((x) => x != null)));
    const bars = series.map((d) => {
      const v = d.sleep_duration != null ? d.sleep_duration : 0;
      const h = Math.round((v / max) * 100);
      return `<i style="height:${h}%" title="${esc(d.date)} sleep ${v ?? "—"}"></i>`;
    }).join("");

    $("patterns-body").innerHTML = `
      <div class="panel">
        <div class="panel-head"><h2>Sleep duration (recent)</h2><span class="tag">Observed averages</span></div>
        <div class="chart-bars" aria-hidden="true">${bars}</div>
        <p class="muted" style="margin-top:8px">${series.length} day-points · y-scale to max ${max.toFixed(1)}</p>
        <details class="derive"><summary>How this was derived</summary>
          <dl>
            <dt>Method</dt><dd>Daily averages from authorized observations</dd>
            <dt>Window</dt><dd>Up to 30 recent day buckets from /api/v1/patterns</dd>
            <dt>Missingness</dt><dd>Days without values omit bars rather than invent zeros</dd>
            <dt>Limitation</dt><dd>Not causal; not clinical</dd>
          </dl>
        </details>
      </div>
      <div class="panel">
        <div class="panel-head"><h2>Summary fields</h2></div>
        <div class="grid-2">
          ${["sleep_duration","stress","focus","energy"].map((k) => {
            const avg = p.averages && p.averages[k];
            return `<div class="stat-card"><div class="label">${esc(k)}</div><div class="value" style="font-size:1.2rem">${avg != null ? avg : "—"}</div></div>`;
          }).join("")}
        </div>
      </div>`;
  }

  function renderResearch() {
    const w = state.weekly;
    if (w) {
      $("research-weekly").innerHTML = `
        <p><b>${esc(w.title || "Weekly report")}</b></p>
        <p class="muted">${esc(w.subtitle || "")}</p>
        ${(w.sections || []).map((s) => `<div style="margin-top:12px"><b>${esc(s.title || s.kind || "Section")}</b><p class="muted">${esc(s.body || "")}</p></div>`).join("")}
        ${w.experiment ? `<p style="margin-top:12px"><b>Bounded experiment idea</b><br><span class="muted">${esc(w.experiment)}</span></p>` : ""}
        <p class="fine">${esc(w.disclaimer || "Descriptive only. Not medical advice.")}</p>
        <details class="derive"><summary>How this was derived</summary>
          <dl>
            <dt>Source</dt><dd>GET /api/v1/reports/weekly</dd>
            <dt>Coverage</dt><dd>${esc(JSON.stringify(w.coverage || {}))}</dd>
            <dt>Status</dt><dd>${esc(w.status || "—")}</dd>
            <dt>Epistemic</dt><dd>Calculated summary over observed lifestyle fields</dd>
          </dl>
        </details>`;
    } else {
      $("research-weekly").innerHTML = `<div class="empty"><b>Weekly report unavailable</b><span>Endpoint returned no payload or requires more data.</span></div>`;
    }

    $("research-engine").innerHTML = `<div class="empty"><b>Engine panel</b><span>Status is loaded when /api/v1/intelligence/engine/status is authorized and implemented for this account. No simulated activity.</span></div>`;
    api("/api/v1/intelligence/engine/status").then((st) => {
      $("research-engine").innerHTML = `<pre class="fine" style="white-space:pre-wrap">${esc(JSON.stringify(st, null, 2))}</pre>`;
    }).catch(() => {});
  }

  function renderMap(selected) {
    const sel = selected || ARCH[0].id;
    $("arch-map").innerHTML = ARCH.map((layer) => `
      <button type="button" class="arch-layer ${layer.id === sel ? "active" : ""}" data-layer="${layer.id}" role="listitem">
        <div>
          <span class="layer-id">${layer.id}</span>
          <b>${esc(layer.title)}</b>
          <p>${esc(layer.purpose)}</p>
        </div>
        ${statusTag(layer.status)}
      </button>`).join("");
    $("arch-map").querySelectorAll("[data-layer]").forEach((btn) => {
      btn.addEventListener("click", () => renderMap(btn.getAttribute("data-layer")));
    });
    const layer = ARCH.find((l) => l.id === sel) || ARCH[0];
    $("arch-detail").innerHTML = `
      <div class="panel-head"><h2>${esc(layer.title)}</h2>${statusTag(layer.status)}</div>
      <dl class="derive" style="border:0;padding:0;margin:0">
        <dt>Purpose</dt><dd>${esc(layer.purpose)}</dd>
        <dt>Inputs</dt><dd>${esc(layer.inputs)}</dd>
        <dt>Outputs</dt><dd>${esc(layer.outputs)}</dd>
        <dt>Dependencies</dt><dd>${esc(layer.deps)}</dd>
        <dt>Note</dt><dd>Conceptual product layer. Implementation status is deployment-honest, not aspirational branding.</dd>
      </dl>`;
  }

  async function renderPrivacy() {
    try {
      state.consent = await api("/api/v1/consent");
    } catch {
      state.consent = null;
    }
    if (!state.consent) {
      $("privacy-body").innerHTML = `<div class="empty"><b>Consent API unavailable</b></div>`;
      return;
    }
    const rows = (state.consent.consents || []).map((c) =>
      `<div class="maturity-row"><div><b>${esc(c.purpose)}</b><div class="muted">Category ${esc(state.consent.data_category || "lifestyle")}</div></div>
      ${c.granted ? statusTag("available") : statusTag("unavailable")}</div>`
    ).join("");
    $("privacy-body").innerHTML = `
      <div class="panel"><div class="panel-head"><h2>Lifestyle purposes</h2><span class="tag">Server-enforced</span></div>
      ${rows || "<p class='muted'>No purpose rows</p>"}
      <p class="fine" style="margin-top:12px">Revoking authorization is enforced on the server. UI toggles cannot bypass backend checks.</p></div>`;
  }

  function renderAccount() {
    const u = state.user || {};
    $("account-body").innerHTML = `
      <div class="panel">
        <div class="stat-card" style="border:0;padding:0">
          <div class="label">Email</div><div class="value" style="font-size:1rem">${esc(u.email || "—")}</div>
          <div class="hint">Verified: ${u.email_verified ? "yes" : "no"} · id ${u.id ?? "—"}</div>
        </div>
      </div>
      <div class="panel">
        <p class="muted">Profile fields load from /api/v1/profile when available.</p>
        <pre class="fine" id="profile-pre" style="white-space:pre-wrap">Loading…</pre>
      </div>`;
    api("/api/v1/profile").then((p) => {
      $("profile-pre").textContent = JSON.stringify(p, null, 2);
    }).catch((e) => {
      $("profile-pre").textContent = String(e.message || e);
    });
  }

  async function loadRoute(name) {
    if (name === "overview") {
      await Promise.all([
        api("/api/v1/timeline").then((d) => { state.timeline = d || []; }).catch(() => { state.timeline = []; }),
        api("/api/v1/signals").then((d) => { state.signals = d; }).catch(() => { state.signals = null; }),
      ]);
      renderOverview();
    } else if (name === "checkin") {
      state.checkinData = {};
      renderCheckin();
    } else if (name === "data") {
      await api("/api/v1/timeline").then((d) => { state.timeline = d || []; }).catch(() => { state.timeline = []; });
      renderData();
    } else if (name === "patterns") {
      await api("/api/v1/patterns?days=30").then((d) => { state.patterns = d; }).catch(() => { state.patterns = null; });
      renderPatterns();
    } else if (name === "research") {
      await api("/api/v1/reports/weekly").then((d) => { state.weekly = d; }).catch(() => { state.weekly = null; });
      renderResearch();
    } else if (name === "map") {
      renderMap();
    } else if (name === "privacy") {
      await renderPrivacy();
    } else if (name === "account") {
      renderAccount();
    }
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function bootShell() {
    setAuthVisible(false);
    $("user-pill").textContent = state.user.email || "signed in";
    try {
      state.health = await api("/api/v1/health");
      $("health-dot").className = "status-dot ok";
      $("health-label").textContent = "API " + (state.health.version || "ok");
    } catch {
      $("health-dot").className = "status-dot err";
      $("health-label").textContent = "API unreachable";
    }
    setRoute("overview");
  }

  // Events
  $("tab-login").addEventListener("click", () => {
    state.authMode = "login";
    $("tab-login").classList.add("active");
    $("tab-register").classList.remove("active");
    $("auth-submit").textContent = "Sign in";
  });
  $("tab-register").addEventListener("click", () => {
    state.authMode = "register";
    $("tab-register").classList.add("active");
    $("tab-login").classList.remove("active");
    $("auth-submit").textContent = "Create account";
  });

  $("auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("auth-error").classList.add("hide");
    const email = $("auth-email").value.trim();
    const password = $("auth-password").value;
    try {
      await refreshCsrf();
      const path = state.authMode === "register" ? "/api/v1/auth/register" : "/api/v1/auth/login";
      await api(path, { method: "POST", body: { email, password }, csrf: true });
      await ensureSession();
      if (!state.user) throw new Error("Session not established");
      await bootShell();
    } catch (err) {
      $("auth-error").textContent = typeof err.data?.detail === "string" ? err.data.detail : (err.message || "Authentication failed");
      $("auth-error").classList.remove("hide");
    }
  });

  $("btn-nav").addEventListener("click", () => $("sidebar").classList.toggle("open"));
  document.querySelectorAll("[data-route]").forEach((btn) => {
    btn.addEventListener("click", () => setRoute(btn.getAttribute("data-route")));
  });

  $("checkin-period").querySelectorAll("[data-period]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.checkinPeriod = btn.getAttribute("data-period");
      state.checkinData = {};
      $("checkin-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
      $("checkin-status").classList.add("hide");
      renderCheckin();
    });
  });

  $("checkin-save").addEventListener("click", async () => {
    const status = $("checkin-status");
    status.classList.remove("hide", "ok", "err");
    const fields = state.checkinPeriod === "morning" ? MORNING : EVENING;
    const values = {};
    for (const f of fields) {
      if (state.checkinData[f.kind] === undefined) {
        status.textContent = `Select a value for ${f.label}.`;
        status.classList.add("err");
        return;
      }
      if (state.checkinData[f.kind] === "skipped") continue;
      values[f.kind] = state.checkinData[f.kind];
    }
    if (!Object.keys(values).length) {
      status.textContent = "Nothing to save.";
      status.classList.add("err");
      return;
    }
    try {
      await refreshCsrf();
      const path = state.checkinPeriod === "morning" ? "/api/v1/checkins/morning" : "/api/v1/checkins/evening";
      const res = await api(path, { method: "POST", body: { values }, csrf: true });
      status.textContent = `Saved ${res.saved || Object.keys(values).length} observation(s). Persistence confirmed by server — not an analysis.`;
      status.classList.add("ok");
      toast("Check-in saved");
    } catch (err) {
      const detail = err.data && err.data.detail;
      status.textContent = typeof detail === "string" ? detail : (err.message || "Save failed");
      status.classList.add("err");
    }
  });

  $("data-filter-kind").addEventListener("change", renderData);

  $("btn-logout").addEventListener("click", async () => {
    try {
      await refreshCsrf();
      await api("/api/v1/auth/logout", { method: "POST", csrf: true });
    } catch { /* still clear UI */ }
    state.user = null;
    setAuthVisible(true);
  });

  // Boot
  (async () => {
    const ok = await ensureSession();
    if (ok) await bootShell();
    else setAuthVisible(true);
  })();
})();