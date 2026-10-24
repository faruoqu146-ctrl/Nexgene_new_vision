(function () {
  var s = document.createElement("script");
  s.src = "/static/app.core.js";
  s.async = false;
  s.onerror = function () {
    console.error("NexGene: failed to load /static/app.core.js");
  };
  document.head.appendChild(s);
})();
