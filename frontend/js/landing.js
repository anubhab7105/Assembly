/* Assembly Landing — canvas network, reveals, counters, hero sim, family lab */
(function () {
  "use strict";
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── mobile nav ── */
  var burger = document.getElementById("burger");
  var mobile = document.getElementById("mobileMenu");
  if (burger && mobile) {
    burger.addEventListener("click", function () {
      var open = mobile.classList.toggle("open");
      burger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    mobile.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () { mobile.classList.remove("open"); });
    });
  }

  /* ── network canvas (agent graph) ── */
  var canvas = document.getElementById("net-canvas");
  if (canvas && !reduceMotion) {
    var ctx = canvas.getContext("2d");
    var W, H, nodes = [], N = 46;
    var COLORS = ["99,102,241", "129,140,248", "167,139,250"];
    function size() {
      W = canvas.width = window.innerWidth;
      H = canvas.height = window.innerHeight;
    }
    function seed() {
      nodes = [];
      for (var i = 0; i < N; i++) {
        nodes.push({
          x: Math.random() * W, y: Math.random() * H,
          vx: (Math.random() - 0.5) * 0.35, vy: (Math.random() - 0.5) * 0.35,
          r: 1.4 + Math.random() * 2.2, c: COLORS[i % 3]
        });
      }
    }
    size(); seed();
    window.addEventListener("resize", function () { size(); seed(); });
    var mx = -9999, my = -9999;
    window.addEventListener("pointermove", function (e) { mx = e.clientX; my = e.clientY; });
    (function frame() {
      ctx.clearRect(0, 0, W, H);
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        n.x += n.vx; n.y += n.vy;
        if (n.x < 0 || n.x > W) n.vx *= -1;
        if (n.y < 0 || n.y > H) n.vy *= -1;
        // gentle mouse attraction
        var dx = mx - n.x, dy = my - n.y, d = Math.hypot(dx, dy);
        if (d < 220 && d > 1) { n.x += dx / d * 0.25; n.y += dy / d * 0.25; }
      }
      // edges
      for (var a = 0; a < nodes.length; a++) {
        for (var b = a + 1; b < nodes.length; b++) {
          var pa = nodes[a], pb = nodes[b];
          var dist = Math.hypot(pa.x - pb.x, pa.y - pb.y);
          if (dist < 150) {
            ctx.strokeStyle = "rgba(99,102,241," + (0.14 * (1 - dist / 150)).toFixed(3) + ")";
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
          }
        }
      }
      // nodes
      for (var k = 0; k < nodes.length; k++) {
        var q = nodes[k];
        ctx.fillStyle = "rgba(" + q.c + ",0.75)";
        ctx.beginPath(); ctx.arc(q.x, q.y, q.r, 0, Math.PI * 2); ctx.fill();
      }
      requestAnimationFrame(frame);
    })();
  }

  /* ── reveal on scroll ── */
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll(".reveal, .metric, .f-row").forEach(function (el) { io.observe(el); });

  /* ── animated counters ── */
  var cio = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      var el = e.target, end = parseInt(el.getAttribute("data-count"), 10);
      if (isNaN(end)) return;
      cio.unobserve(el);
      if (reduceMotion) { el.textContent = end; return; }
      var t0 = performance.now(), dur = 1400;
      (function tick(t) {
        var p = Math.min((t - t0) / dur, 1);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(end * eased).toLocaleString("en-US");
        if (p < 1) requestAnimationFrame(tick);
      })(t0);
    });
  }, { threshold: 0.5 });
  document.querySelectorAll("[data-count]").forEach(function (el) { cio.observe(el); });

  /* ── marquee: duplicate for seamless loop ── */
  var track = document.getElementById("marqueeTrack");
  if (track) { track.innerHTML += track.innerHTML; }

  /* ── rotating hero questions ── */
  var questions = [
    "Compare React, Vue and Svelte for a large-scale dashboard…",
    "Explain TCP vs UDP — when does each win in production?",
    "Write a Python fn: longest palindromic substring, O(n)…",
    "Best strategies to cut urban-transport emissions?"
  ];
  var tq = document.getElementById("typedQ"), qi = 0;
  if (tq && !reduceMotion) {
    setInterval(function () {
      qi = (qi + 1) % questions.length;
      tq.style.opacity = "0";
      setTimeout(function () { tq.textContent = questions[qi]; tq.style.opacity = "1"; }, 280);
    }, 4200);
    tq.style.transition = "opacity .28s ease";
  }

  /* ── hero dashboard simulation ── */
  var cfill = document.getElementById("cfill");
  var cval = document.getElementById("cval");
  var feed = document.getElementById("dashFeed");
  var timer = document.getElementById("dashTimer");
  var agents = Array.prototype.slice.call(document.querySelectorAll("#dashAgents .agent"));
  var budgets = document.querySelectorAll("#dashBudgets button");
  var feedLines = [
    ["00:04", "planning", "fi-plan", "Planner: general · medium → 4 agents, 3 rounds"],
    ["00:21", "solving", "fi-solve", "Solver (gemini): position published · conf 0.82"],
    ["00:38", "solving", "fi-solve", "Researcher (qwen): 3 sources cited, 2 verified"],
    ["01:02", "debating", "fi-debate", "Critic (gpt-oss): disagrees_with [solver] — SSR gap"],
    ["01:40", "debating", "fi-debate", "new_info_rate +0.21 · stabilization converging"],
    ["02:15", "synthesizing", "fi-synth", "Synthesizer (nemotron): composing + citations [1–5]"],
    ["02:31", "synthesizing", "fi-synth", "Consensus 0.87 · HIGH — finalizing answer"]
  ];
  var state = { min: 5, left: 4 * 60 + 37, score: 0, li: 0, timerId: null, feedId: null };

  function mmss(s) {
    var m = Math.floor(s / 60), sec = s % 60;
    return (m < 10 ? "0" + m : m) + ":" + (sec < 10 ? "0" + sec : sec);
  }
  function pushFeed(line) {
    if (!feed) return;
    var div = document.createElement("div");
    div.className = "feed-item";
    div.innerHTML = "<time>" + line[0] + "</time><i class='" + line[2] + "'></i><span>" + line[3] + "</span>";
    feed.appendChild(div);
    while (feed.querySelectorAll(".feed-item").length > 5) {
      feed.removeChild(feed.querySelector(".feed-item"));
    }
  }
  function resetSim() {
    if (!cfill) return;
    state.score = 0; state.li = 0;
    state.left = state.min * 60 - 23;
    cfill.style.width = "0%"; if (cval) cval.textContent = "0%";
    if (feed) feed.querySelectorAll(".feed-item").forEach(function (n) { n.remove(); });
    agents.forEach(function (a, i) {
      a.classList.toggle("active", i < 2);
      a.classList.remove("done");
      a.querySelector("em").textContent = i < 2 ? (i === 0 ? "solving…" : "searching…") : "queued";
    });
  }
  function stepSim() {
    // consensus climbs in S-curve toward 87
    state.score = Math.min(87, state.score + 3 + Math.random() * 5);
    if (cfill) cfill.style.width = state.score.toFixed(0) + "%";
    if (cval) cval.textContent = state.score.toFixed(0) + "%";
    if (state.li < feedLines.length && state.score > (state.li + 1) * 11) {
      pushFeed(feedLines[state.li]);
      var ag = agents[Math.min(state.li, agents.length - 1)];
      if (ag) {
        ag.classList.add("done"); ag.classList.remove("active");
        var em = ag.querySelector("em"); if (em) em.textContent = "✓ published";
        var next = agents[state.li + 1];
        if (next) { next.classList.add("active"); var ne = next.querySelector("em"); if (ne) ne.textContent = "working…"; }
      }
      state.li++;
    }
    if (state.score >= 87) { resetSim(); }
  }
  function tickTimer() {
    if (state.left > 0) state.left--;
    else state.left = state.min * 60;
    if (timer) timer.textContent = mmss(state.left);
  }
  if (cfill && !reduceMotion) {
    cfill.style.transition = "width .8s cubic-bezier(.4,0,.2,1)";
    state.timerId = setInterval(tickTimer, 1000);
    state.feedId = setInterval(stepSim, 1100);
    tickTimer(); stepSim();
  } else if (cfill) {
    cfill.style.width = "87%"; if (cval) cval.textContent = "87%";
    feedLines.forEach(pushFeed);
  }
  budgets.forEach(function (b) {
    b.addEventListener("click", function () {
      budgets.forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on");
      state.min = parseInt(b.getAttribute("data-min"), 10) || 5;
      resetSim();
    });
  });

  /* ── tilt cards ── */
  if (!reduceMotion && window.matchMedia("(pointer:fine)").matches) {
    document.querySelectorAll(".tilt").forEach(function (card) {
      card.addEventListener("pointermove", function (e) {
        var r = card.getBoundingClientRect();
        var rx = ((e.clientY - r.top) / r.height - 0.5) * -7;
        var ry = ((e.clientX - r.left) / r.width - 0.5) * 7;
        card.style.transform = "translateY(-6px) perspective(900px) rotateX(" + rx.toFixed(2) + "deg) rotateY(" + ry.toFixed(2) + "deg)";
      });
      card.addEventListener("pointerleave", function () { card.style.transform = ""; });
    });
    var dash = document.getElementById("dash");
    if (dash) {
      dash.addEventListener("pointermove", function (e) {
        var r = dash.getBoundingClientRect();
        var rx = ((e.clientY - r.top) / r.height - 0.5) * -4;
        var ry = ((e.clientX - r.left) / r.width - 0.5) * 4;
        dash.style.transform = "perspective(1200px) rotateX(" + rx.toFixed(2) + "deg) rotateY(" + ry.toFixed(2) + "deg)";
      });
      dash.addEventListener("pointerleave", function () { dash.style.transform = ""; });
    }
  }

  /* ── diversity lab ── */
  var famBtns = document.querySelectorAll("#famGrid .fam");
  var famStatus = document.getElementById("famStatus");
  function famUpdate() {
    var on = document.querySelectorAll("#famGrid .fam.on").length;
    if (!famStatus) return;
    famStatus.classList.remove("warn", "bad");
    if (on >= 3) {
      famStatus.textContent = "● " + on + " families · debate valid — critic assigned off solver families";
    } else if (on === 2) {
      famStatus.textContent = "▲ 2 families · runs with visible warning — same-family votes merged";
      famStatus.classList.add("warn");
    } else {
      famStatus.textContent = "■ " + on + " famil" + (on === 1 ? "y" : "ies") + " · DEGRADED — answer flagged, no silent consensus";
      famStatus.classList.add("bad");
    }
  }
  famBtns.forEach(function (b) {
    b.addEventListener("click", function () { b.classList.toggle("on"); famUpdate(); });
  });
})();
