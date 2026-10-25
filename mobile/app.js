(async function () {
  try {
    var parts = ["app.c0.js", "app.c1.js", "app.c2.js", "app.c3.js"];
    var code = "";
    for (var i = 0; i < parts.length; i++) {
      var r = await fetch("/static/" + parts[i], { credentials: "same-origin" });
      if (!r.ok) throw new Error("missing " + parts[i]);
      code += await r.text();
    }
    var s = document.createElement("script");
    s.text = code;
    document.head.appendChild(s);
  } catch (e) {
    console.error("NexGene UI load failed", e);
  }
})();
