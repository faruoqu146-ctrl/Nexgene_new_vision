/* NexGene fx — presentation only; no product state */
(function () {
  'use strict';
  function prefersReduced() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }
  function helix(canvas) {
    if (!canvas || prefersReduced()) return;
    var ctx = canvas.getContext('2d');
    if (!ctx) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w, h, t = 0, raf;
    function resize() {
      var r = canvas.parentElement.getBoundingClientRect();
      w = Math.max(1, r.width); h = Math.max(1, r.height);
      canvas.width = w * dpr; canvas.height = h * dpr;
      canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    function draw() {
      ctx.clearRect(0, 0, w, h);
      var cx = w * 0.48, cy = h * 0.5;
      var pairs = 14, turns = 2.2;
      for (var i = 0; i < pairs; i++) {
        var p = i / pairs;
        var a = p * Math.PI * 2 * turns + t;
        var y = cy + (p - 0.5) * h * 0.72;
        var r = 18 + Math.sin(p * Math.PI) * 28;
        var x1 = cx + Math.cos(a) * r;
        var x2 = cx + Math.cos(a + Math.PI) * r;
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(134,214,194,' + (0.15 + 0.35 * (1 - Math.abs(p - 0.5) * 2)) + ')';
        ctx.lineWidth = 1.2;
        ctx.moveTo(x1, y); ctx.lineTo(x2, y); ctx.stroke();
        ctx.beginPath(); ctx.fillStyle = 'rgba(134,214,194,0.55)'; ctx.arc(x1, y, 2.2, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.fillStyle = 'rgba(217,179,108,0.5)'; ctx.arc(x2, y, 2.2, 0, Math.PI * 2); ctx.fill();
      }
      t += 0.008; raf = requestAnimationFrame(draw);
    }
    resize(); draw();
    window.addEventListener('resize', resize, { passive: true });
    return function stop() { cancelAnimationFrame(raf); };
  }
  function boot() {
    var c = document.getElementById('helix');
    if (c) helix(c);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
