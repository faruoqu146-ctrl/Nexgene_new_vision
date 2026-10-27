(function () {
  var s = document.createElement("script");
  s.src = "/static/app.core.js";
  s.async = false;
  s.onerror = function () {
    console.error("NexGene: failed to load /static/app.core.js");
    var el = document.getElementById("auth-error");
    if (el) {
      el.classList.remove("hide");
      el.textContent = "UI client failed to load. Hard-refresh or redeploy mobile/app.core.js.";
    }
  };
  document.head.appendChild(s);
})();
