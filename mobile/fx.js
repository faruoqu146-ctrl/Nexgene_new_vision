/* NexGene fx — presentation only; touches no app state or API */
(() => {
  const $ = (id) => document.getElementById(id);
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Sign-in hero: a slow, fine-line double helix. Typing quickens it and lights a base pair.
  const hero = document.querySelector(".auth-hero"), cv = $("helix");
  if (hero && cv) {
    const c = cv.getContext("2d");
    let W, H, t = 0, boost = 0, mx = 0;
    const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    const size = () => {
      const d = devicePixelRatio || 1;
      W = hero.clientWidth; H = hero.clientHeight;
      cv.width = W * d; cv.height = H * d; c.setTransform(d, 0, 0, d, 0, 0);
      if (still) draw();
    };
    function draw() {
      const A = css("--a"), B = css("--b"), T = css("--text2"), step = 11;
      const L = Math.hypot(W, H), amp = Math.min(W, H) * 0.13, wide = W > H * 1.3;
      c.clearRect(0, 0, W, H); c.save();
      c.translate(wide ? W * 0.5 : W * 0.7, H * 0.5);
      c.rotate((wide ? Math.PI / 2 : 0.2) + mx * 0.05);
      let pa = null, pb = 0, i = 0;
      for (let y = -L / 2; y < L / 2; y += step, i++) {
        const p = y * 0.0105 + t, xa = amp * Math.sin(p), xb = -xa, ka = (Math.cos(p) + 1) / 2, kb = 1 - ka;
        if (pa !== null) {
          c.lineWidth = 0.8 + 1.4 * ka; c.globalAlpha = 0.18 + 0.62 * ka; c.strokeStyle = A;
          c.beginPath(); c.moveTo(pa, y - step); c.lineTo(xa, y); c.stroke();
          c.lineWidth = 0.8 + 1.4 * kb; c.globalAlpha = 0.14 + 0.5 * kb; c.strokeStyle = T;
          c.beginPath(); c.moveTo(pb, y - step); c.lineTo(xb, y); c.stroke();
        }
        pa = xa; pb = xb;
        if (i % 3 === 0) {
          const lit = (i + (t * 5 | 0)) % 31 === 0;
          c.globalAlpha = lit ? 0.85 : 0.1; c.strokeStyle = lit ? B : T; c.lineWidth = 1;
          c.beginPath(); c.moveTo(xa, y); c.lineTo(xb, y); c.stroke();
        }
      }
      c.restore(); c.globalAlpha = 1;
    }
    size(); addEventListener("resize", size);
    if (!still) {
      (function loop() {
        t += 0.006 + boost; boost *= 0.95;
        if (hero.offsetParent !== null) draw();
        requestAnimationFrame(loop);
      })();
      hero.addEventListener("pointermove", (e) => { mx = e.clientX / W - 0.5; });
      ["auth-email", "auth-password"].forEach((id) => $(id).addEventListener("input", () => { boost = Math.min(0.05, boost + 0.012); }));
    }
  }

  // Overview: the headline figure counts up once when it renders.
  const stats = $("overview-stats");
  if (stats && !still) new MutationObserver(() => {
    const el = stats.querySelector(".stat-card:first-child .value");
    const n = el ? +el.textContent : NaN;
    if (!el || !Number.isInteger(n) || el.dataset.done) return;
    el.dataset.done = 1;
    const s = performance.now();
    (function f(now) {
      const k = Math.min(1, (now - s) / 800);
      el.textContent = Math.round(n * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(f);
    })(s);
  }).observe(stats, { childList: true });

  // Sign-in: show/hide password; focus email on desktop.
  const pw = $("auth-password"), tg = $("pw-toggle");
  if (pw && tg) tg.addEventListener("click", () => {
    const show = pw.type === "password";
    pw.type = show ? "text" : "password";
    tg.textContent = show ? "Hide" : "Show";
    tg.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
  if (!matchMedia("(pointer:coarse)").matches && $("auth-email")) $("auth-email").focus();

  // Check-in: progress, count, and a gentle glide to the next unanswered question.
  const form = $("checkin-form"), bar = $("ck-prog"), cnt = $("ck-count");
  let adv = false;
  if (form) {
    form.addEventListener("click", (e) => { if (e.target.closest(".choice")) adv = true; }, true);
    new MutationObserver(() => {
      const ps = [...form.querySelectorAll(".panel")], done = ps.filter((p) => p.querySelector(".choice.selected"));
      if (bar) bar.style.width = (ps.length ? (done.length / ps.length) * 100 : 0) + "%";
      if (cnt) cnt.textContent = done.length + " of " + ps.length;
      const next = ps.find((p) => !p.querySelector(".choice.selected"));
      if (adv && next) next.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "center" });
      adv = false;
    }).observe(form, { childList: true, subtree: true });
    // Evenings default to the evening check-in.
    if (new Date().getHours() >= 15) document.querySelector('[data-period="evening"]')?.click();
  }

  // Patterns: drag across any line to read a single day.
  const pat = $("patterns-body");
  if (pat) {
    const show = (sp, i) => {
      const v = JSON.parse(sp.dataset.v), d = JSON.parse(sp.dataset.d), m = +sp.dataset.m;
      if (i < 0 || i >= v.length || v[i] == null) return;
      const x = (v.length > 1 ? (i / (v.length - 1)) * 100 : 50) + "%", row = sp.closest(".spark-row");
      const dot = sp.querySelector(".spark-dot");
      dot.style.left = sp.querySelector(".spark-cur").style.left = x;
      dot.style.top = ((38 - (v[i] / m) * 36) / 40) * 100 + "%";
      row.querySelector(".spark-val b").textContent = v[i];
      row.querySelector(".spark-val small").textContent = d[i] || "";
    };
    pat.addEventListener("pointermove", (e) => {
      const sp = e.target.closest(".spark");
      if (!sp) return;
      const r = sp.getBoundingClientRect(), n = JSON.parse(sp.dataset.v).length;
      show(sp, Math.round(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * (n - 1)));
    });
    pat.addEventListener("pointerleave", (e) => {
      if (e.target.classList && e.target.classList.contains("spark")) show(e.target, +e.target.dataset.l);
    }, true);
  }
})();
