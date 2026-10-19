(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Scroll reveal
  var items = document.querySelectorAll(".reveal");
  if (reduce || !("IntersectionObserver" in window)) {
    items.forEach(function (el) { el.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add("in");
        io.unobserve(e.target);
        if (e.target.classList.contains("terminal")) typeCode();
      });
    }, { threshold: 0.15 });
    items.forEach(function (el) { io.observe(el); });
  }

  // Staggered feature list
  document.querySelectorAll(".features li").forEach(function (li, i) {
    li.style.transitionDelay = 0.15 + i * 0.08 + "s";
  });

  // Typing effect for the curl example
  function typeCode() {
    var code = document.getElementById("typed");
    if (!code || reduce) return;
    var text = code.getAttribute("data-text")
      .replace(/&gt;/g, ">").replace(/&lt;/g, "<").replace(/&amp;/g, "&");
    var caret = document.createElement("span");
    caret.className = "caret";
    code.textContent = "";
    var node = document.createTextNode("");
    code.appendChild(node);
    code.appendChild(caret);
    var i = 0;
    (function tick() {
      node.data = text.slice(0, ++i);
      if (i < text.length) setTimeout(tick, text[i - 1] === "\n" ? 180 : 14 + Math.random() * 22);
    })();
  }

  // Live stats from the published Parquet manifest
  var stats = document.getElementById("stats");
  if (stats && window.fetch) {
    fetch("/api/salud")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (m) {
        if (!m || !m.total_licitaciones) return;
        stats.classList.remove("hidden");
        stats.querySelectorAll("[data-count]").forEach(function (el) {
          var scale = Number(el.getAttribute("data-scale") || 1);
          countUp(el, Math.round(Number(m[el.getAttribute("data-count")] || 0) / scale));
        });
        var desde = m.desde ? String(m.desde).slice(0, 4) : null;
        var upd = m.ultima_actualizacion ? String(m.ultima_actualizacion).slice(0, 10) : null;
        document.getElementById("stats-note").textContent =
          "Datos de la PLACSP" + (desde ? " desde " + desde : "") + (upd ? " · actualizado " + upd : "");
      })
      .catch(function () {});
  }

  function countUp(el, target) {
    var fmt = function (n) { return n.toLocaleString("es-ES"); };
    if (reduce) { el.textContent = fmt(target); return; }
    var start = null, dur = 1400;
    (function step(t) {
      if (start === null) start = t;
      var p = Math.min((t - start) / dur, 1);
      el.textContent = fmt(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(step);
    })(performance.now());
  }

  // Hero background: dot grid with travelling pulses
  var canvas = document.getElementById("hero-bg");
  if (!canvas || reduce) return;
  var ctx = canvas.getContext("2d");
  var gap = 22, w, h, dpr, cols, rows, pulses = [], mouse = { x: -1e4, y: -1e4 };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cols = Math.ceil(w / gap) + 1; rows = Math.ceil(h / gap) + 1;
  }

  function spawn() {
    pulses.push({ x: Math.random() * w, y: Math.random() * h, r: 0, life: 1 });
  }

  canvas.parentElement.addEventListener("pointermove", function (e) {
    var b = canvas.getBoundingClientRect();
    mouse.x = e.clientX - b.left; mouse.y = e.clientY - b.top;
  });
  canvas.parentElement.addEventListener("pointerleave", function () {
    mouse.x = mouse.y = -1e4;
  });

  var last = 0, visible = true;
  new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }).observe(canvas);

  function frame(t) {
    requestAnimationFrame(frame);
    if (!visible) return;
    if (t - last > 700) { spawn(); last = t; }
    ctx.clearRect(0, 0, w, h);
    pulses.forEach(function (p) { p.r += 1.6; p.life -= 0.006; });
    pulses = pulses.filter(function (p) { return p.life > 0; });
    for (var i = 0; i < cols; i++) {
      for (var j = 0; j < rows; j++) {
        var x = i * gap, y = j * gap, a = 0.16;
        for (var k = 0; k < pulses.length; k++) {
          var p = pulses[k], d = Math.abs(Math.hypot(x - p.x, y - p.y) - p.r);
          if (d < 22) a += (1 - d / 22) * 0.75 * p.life;
        }
        var md = Math.hypot(x - mouse.x, y - mouse.y);
        if (md < 120) a += (1 - md / 120) * 0.5;
        ctx.fillStyle = "rgba(17,17,17," + Math.min(a, 0.85) + ")";
        ctx.fillRect(x - 1.25, y - 1.25, 2.5, 2.5);
      }
    }
  }

  resize();
  window.addEventListener("resize", resize);
  spawn();
  requestAnimationFrame(frame);
})();
