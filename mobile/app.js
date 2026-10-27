/* PLACEHOLDER loader: points at app.core.js
 * Prefer pasting V4_app.js if you want the exact zip loader fixed to app.core.js.
 */
(function () {
  var s = document.createElement("script");
  s.src = "/static/app.core.js";
  s.async = false;
  s.onerror = function () {
    console.error("NexGene: failed to load /static/app.core.js (placeholder or missing)");
  };
  document.head.appendChild(s);
})();
