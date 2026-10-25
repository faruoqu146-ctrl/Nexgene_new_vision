/* NexGene fx — presentation only; touches no app state or API */
(() => {
  const $ = (id) => document.getElementById(id);
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Auth hero: a living double helix. Typing makes it spin faster and lights base pairs.
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
      const A = css("--a"), B = css("--b"), L = Math.hypot(W, H), amp = Math.min(W, H) * 0.2;
      c.clearRect(0, 0, W, H); c.save();
      c.translate(W * 0.55, H * 0.45); c.rotate(-0.62 + mx * 0.08);
      for (let x = -L / 2; x < L / 2; x += 14) {
        const p = x * 0.011 + t, z = Math.cos(p), y1 = amp * Math.sin(p);
        const lit = ((x / 14 | 0) + (t * 6 | 0)) % 23 === 0;
        c.globalAlpha = 0.14 + 0.16 * Math.abs(z) + (lit ? 0.55 : 0);
        c.strokeStyle = lit ? B : A; c.lineWidth = 1;
        c.beginPath(); c.moveTo(x, y1); c.lineTo(x, -y1); c.stroke();
        for (const [y, col, d] of [[y1, A, z], [-y1, B, -z]]) {
          const k = (d + 1) / 2;
          c.globalAlpha = 0.3 + 0.7 * k; c.fillStyle = col;
          c.beginPath(); c.arc(x, y, 2 + 3 * k, 0, 6.283); c.fill();
        }
      }
      c.restore(); c.globalAlpha = 1;
    }
    size(); addEventListener("resize", size);
    if (!still) {
      (function loop() {
        t += 0.012 + boost; boost *= 0.94;
        if (hero.offsetParent !== null) draw();
        requestAnimationFrame(loop);
      })();
      hero.addEventListener("pointermove", (e) => { mx = e.clientX / W - 0.5; });
      ["auth-email", "auth-password"].forEach((id) => $(id).addEventListener("input", () => { boost = Math.min(0.12, boost + 0.03); }));
    }
  }

  // Overview numbers count up when they render.
  const stats = $("overview-stats");
  if (stats && !still) new MutationObserver(() => {
    stats.querySelectorAll(".value").forEach((el) => {
      const n = +el.textContent;
      if (!Number.isInteger(n) || el.dataset.done) return;
      el.dataset.done = 1;
      const s = performance.now();
      (function f(now) {
        const k = Math.min(1, (now - s) / 700);
        el.textContent = Math.round(n * (1 - Math.pow(1 - k, 3)));
        if (k < 1) requestAnimationFrame(f);
      })(s);
    });
  }).observe(stats, { childList: true });

  // Check-in progress rail.
  const form = $("checkin-form"), bar = $("ck-prog");
  if (form && bar) new MutationObserver(() => {
    const g = form.querySelectorAll(".choice-grid").length, s = form.querySelectorAll(".choice.selected").length;
    bar.style.width = (g ? (s / g) * 100 : 0) + "%";
  }).observe(form, { childList: true, subtree: true });
})();
