/*
 * landing.js — the three moving moments on the landing page.
 *
 *   hero    the sentence becomes evidence: a declaration is typed, compiled,
 *           scanned and sealed; one in four fails, because a hero in which
 *           everything passes is advertising, not evidence.
 *   chain   the ledger that cannot be edited: records are appended, an old one
 *           is edited, and every link after it breaks.
 *   estate  grey until proven: datasets warm as controls run, and a failure
 *           drains trust from everything downstream along lineage.
 *
 * Only one plays at a time — whichever is most on screen — so the page never
 * becomes a light show. Each draws its still frame first; a reader who asked
 * for less motion gets only that. Colours are read from the theme's tokens
 * and follow a theme change without a reload.
 *
 * Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 */
(function () {
  "use strict";

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var token = function (name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); };
  var fmt = function (n) { return Number(n).toLocaleString("en-GB"); };

  /* ---- which study may move: the one most on screen ---------------------- */
  var ratios = {}, active = null, waiters = [];
  function elect() {
    var best = null, top = 0.35;
    Object.keys(ratios).forEach(function (k) { if (ratios[k] > top) { top = ratios[k]; best = k; } });
    active = best;
    waiters = waiters.filter(function (w) { if (w.name === active) { w.go(); return false; } return true; });
  }
  function turn(name) {
    if (active === name) { return Promise.resolve(); }
    return new Promise(function (go) { waiters.push({ name: name, go: go }); });
  }
  var watcher = "IntersectionObserver" in window ? new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { ratios[e.target.getAttribute("data-study")] = e.intersectionRatio; });
    elect();
  }, { threshold: [0, 0.2, 0.35, 0.5, 0.75, 1] }) : null;
  function register(el, name) {
    el.setAttribute("data-study", name);
    if (watcher) { watcher.observe(el); } else { ratios[name] = name === "hero" ? 1 : 0; elect(); }
  }

  /* ---- hero: the sentence becomes evidence ------------------------------- */
  var HASH = ["9f3a…c1", "2be0…7d", "c41d…09", "5a77…e3"];
  function hero(root) {
    var list = JSON.parse(root.getAttribute("data-declarations") || "[]");
    var said = root.querySelector("[data-said]"), pql = root.querySelector("[data-pql]"),
        run = root.querySelector("[data-run]"), seal = root.querySelector("[data-seal]");
    if (!list.length || reduce) { return; }
    register(root, "hero");
    (async function () {
      for (var loop = 1; ; loop++) {
        await wait(2400);
        var d = list[loop % list.length];
        await turn("hero");
        said.textContent = ""; pql.style.opacity = 0; run.textContent = ""; seal.classList.add("lp-off");
        for (var i = 1; i <= d.said.length; i++) { await turn("hero"); said.textContent = d.said.slice(0, i); await wait(42); }
        await wait(350); pql.textContent = d.pql; pql.style.opacity = 1; await wait(650);
        for (var s = 1; s <= 24; s++) {
          await turn("hero");
          var v = Math.round(d.violations * s / 24);
          run.textContent = "scanned " + fmt(Math.round(d.rows * s / 24)) + " rows · " + v + " violation" + (v === 1 ? "" : "s");
          await wait(45);
        }
        var ok = d.violations === 0;
        seal.className = "lp-seal " + (ok ? "lp-pass" : "lp-fail");
        seal.innerHTML = (ok ? "PASS" : "FAIL · " + d.violations) + " <small>evidence sealed · sha256 " + HASH[loop % HASH.length] + "</small>";
      }
    }());
  }

  /* ---- chain: the ledger that cannot be edited --------------------------- */
  var RECORDS = [
    ["run 0412", "PASS", "p", "7c21…e0"], ["run 0413", "PASS", "p", "a90f…3b"], ["run 0414", "FAIL 17", "f", "44d2…81"],
    ["run 0415", "PASS", "p", "e6b3…0c"], ["run 0416", "PASS", "p", "19ac…f7"]
  ];
  function chain(root) {
    var links = root.querySelector("[data-links]"), status = root.querySelector("[data-status]");
    function fits() { return Math.max(3, Math.min(RECORDS.length, Math.floor((links.clientWidth + 22) / 134))); }
    function record(r) {
      var el = document.createElement("div");
      el.className = "lp-rec";
      el.innerHTML = '<div class="id"></div><div></div><div class="h"></div>';
      el.children[0].textContent = r[0]; el.children[1].textContent = r[1];
      el.children[1].className = r[2]; el.children[2].textContent = r[3];
      return el;
    }
    function hook() { var h = document.createElement("div"); h.className = "lp-hook"; return h; }
    function still() {
      var n = fits(); links.innerHTML = "";
      for (var i = 0; i < n; i++) { if (i) { links.appendChild(hook()); } links.appendChild(record(RECORDS[i])); }
      status.className = "lp-chain-status";
      status.textContent = "chain verified · " + n + " records · head " + RECORDS[n - 1][3];
      return n;
    }
    still();
    if (reduce) { return; }
    register(root, "chain");
    (async function () {
      for (;;) {
        await turn("chain");
        var n = fits(); links.innerHTML = ""; status.className = "lp-chain-status";
        for (var i = 0; i < n; i++) {
          await turn("chain");
          if (i) { links.appendChild(hook()); }
          var el = record(RECORDS[i]); el.classList.add("lp-new"); links.appendChild(el);
          await wait(30); el.classList.remove("lp-new");
          status.textContent = "sealed " + RECORDS[i][0] + " · previous " + (i ? RECORDS[i - 1][3] : "genesis");
          await wait(650);
        }
        status.textContent = "chain verified · " + n + " records · head " + RECORDS[n - 1][3];
        await wait(1800); await turn("chain");
        var recs = links.querySelectorAll(".lp-rec"), hooks = links.querySelectorAll(".lp-hook"), t = 1;
        recs[t].classList.add("lp-tamper");
        status.textContent = "someone edits " + RECORDS[t][0] + "…";
        await wait(900);
        for (var j = t; j < hooks.length; j++) {
          await turn("chain"); hooks[j].classList.add("lp-broken"); recs[j + 1].classList.add("lp-bad"); await wait(260);
        }
        recs[t].classList.remove("lp-tamper"); recs[t].classList.add("lp-bad");
        status.className = "lp-chain-status lp-alarm";
        status.textContent = "chain broken at " + RECORDS[t][0] + " · its hash no longer matches · " + (n - t - 1) + " later records unverifiable";
        await wait(4200);
      }
    }());
  }

  /* ---- estate: grey until proven ----------------------------------------- */
  function estate(root) {
    var cv = root.querySelector("canvas"), ctx = cv.getContext && cv.getContext("2d");
    if (!ctx) { return; }
    var DPR = Math.min(window.devicePixelRatio || 1, 2), W = 0, H = 0, nodes = [], edges = [];
    var seed = 7;
    function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
    for (var c = 0; c < 7; c++) {
      for (var r = 0; r < 4; r++) {
        nodes.push({ x: (c + 0.5) / 7 + (rnd() - 0.5) * 0.06, y: 0.08 + (r + 0.5) / 4 * 0.78 + (rnd() - 0.5) * 0.05,
          at: 0.6 + rnd() * 9, fail: rnd() < 0.1, col: c });
      }
    }
    nodes.forEach(function (n, i) {
      nodes.forEach(function (m, j) { if (m.col === n.col + 1 && Math.abs(m.y - n.y) < 0.24 && rnd() < 0.7) { edges.push([i, j]); } });
    });
    function downstream(i, seen) {
      edges.forEach(function (e) { if (e[0] === i && !seen[e[1]]) { seen[e[1]] = 1; downstream(e[1], seen); } });
      return seen;
    }
    function size() {
      var box = cv.getBoundingClientRect(); W = box.width; H = box.height;
      cv.width = Math.round(W * DPR); cv.height = Math.round(H * DPR); ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }
    function draw(t) {
      var C = { grey: token("--unverified-grey"), pass: token("--dim-completeness"), fail: token("--dim-validity"),
        acc: token("--accent"), line: token("--border-color") };
      ctx.clearRect(0, 0, W, H);
      var dim = {};
      nodes.forEach(function (n, i) {
        if (n.fail && t > n.at) {
          var d = downstream(i, {});
          Object.keys(d).forEach(function (k) { dim[k] = Math.max(dim[k] || 0, Math.min(1, (t - n.at) / 1.2)); });
        }
      });
      edges.forEach(function (e) {
        var a = nodes[e[0]], b = nodes[e[1]], lit = t > a.at && t > b.at, mx = (a.x + b.x) / 2 * W;
        ctx.strokeStyle = lit ? C.acc : C.line; ctx.globalAlpha = lit ? 0.55 : 0.9; ctx.lineWidth = lit ? 1.4 : 1;
        ctx.beginPath(); ctx.moveTo(a.x * W, a.y * H); ctx.bezierCurveTo(mx, a.y * H, mx, b.y * H, b.x * W, b.y * H); ctx.stroke();
      });
      nodes.forEach(function (n, i) {
        var on = t > n.at, k = on ? Math.min(1, (t - n.at) / 0.6) : 0, col = !on ? C.grey : n.fail ? C.fail : C.pass;
        ctx.globalAlpha = on && dim[i] && !n.fail ? 1 - 0.6 * dim[i] : (on ? 0.5 + 0.5 * k : 0.55);
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(n.x * W, n.y * H, 5 + 2.5 * k, 0, Math.PI * 2); ctx.fill();
        if (on && k < 1) {
          ctx.globalAlpha = (1 - k) * 0.5; ctx.strokeStyle = col; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(n.x * W, n.y * H, 8 + 14 * k, 0, Math.PI * 2); ctx.stroke();
        }
      });
      ctx.globalAlpha = 1;
    }
    var clock = 99, last = null;
    size(); draw(clock);
    window.addEventListener("resize", function () { size(); draw(clock); });
    new MutationObserver(function () { draw(clock); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    if (reduce) { return; }
    register(root, "estate");
    var started = false;
    function frame(now) {
      if (active === "estate") {
        // Rests on the finished estate until first seen, then plays from grey.
        if (!started) { started = true; clock = 0; }
        if (last !== null) { clock = (clock + (now - last) / 1000) % 13; }
        last = now; draw(clock);
      } else { last = null; }
      window.requestAnimationFrame(frame);
    }
    window.requestAnimationFrame(frame);
  }

  var h = document.querySelector("[data-lp-hero]"); if (h) { hero(h); }
  var c = document.querySelector("[data-lp-chain]"); if (c) { chain(c); }
  var e = document.querySelector("[data-lp-estate]"); if (e) { estate(e); }
}());
