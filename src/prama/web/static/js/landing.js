/*
 * landing.js — the network behind the landing page's headline.
 *
 * Adopted from Maya. Sources on the left, the people who must trust a number
 * on the right, and Prama in the middle: data travels in, evidence travels
 * out. Colours are read from the theme's tokens and re-read when the theme
 * changes; a reader who asked for less motion gets it drawn once, still.
 *
 * Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 */
(function () {
  "use strict";

  var canvas = document.getElementById("lpNet");
  if (!canvas || !canvas.getContext) { return; }
  var ctx = canvas.getContext("2d");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var SOURCES = ["Warehouse", "Trade feed", "Ledger", "Market data", "CSV drop", "Kafka topic"];
  var READERS = ["Data owner", "Steward", "Auditor", "Regulator", "Attestation", "Evidence bundle"];

  var colour = {};
  function readColours() {
    var css = getComputedStyle(document.documentElement);
    function tok(n, d) { return (css.getPropertyValue(n) || d).trim(); }
    colour = {
      accent: tok("--accent", "#2B3FA8"),
      deep: tok("--text-link", "#2B3FA8"),
      line: tok("--text-muted", "#636A85"),
      label: tok("--text-muted", "#636A85")
    };
  }

  var DPR = Math.min(window.devicePixelRatio || 1, 2);
  var W = 0, H = 0, hub = { x: 0, y: 0 }, left = [], right = [], packets = [];

  function layout() {
    var r = canvas.getBoundingClientRect();
    W = r.width; H = r.height;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    hub.x = W * 0.5; hub.y = H * 0.5;
    var narrow = W < 820;
    var lx = W * (narrow ? 0.06 : 0.1), rx = W * (narrow ? 0.94 : 0.9);
    var top = H * 0.16, bot = H * 0.84;
    left = []; right = [];
    for (var i = 0; i < SOURCES.length; i++) {
      var f = i / (SOURCES.length - 1);
      var y = top + (bot - top) * f;
      var bow = Math.sin(f * Math.PI) * W * 0.035;
      left.push({ x: lx - bow, y: y, label: SOURCES[i] });
      right.push({ x: rx + bow, y: y, label: READERS[i] });
    }
  }

  function spawn() {
    var inbound = Math.random() < 0.5;
    var end = (inbound ? left : right)[Math.floor(Math.random() * left.length)];
    packets.push({ from: inbound ? end : hub, to: inbound ? hub : end, t: 0,
      speed: 0.004 + Math.random() * 0.004, inbound: inbound });
  }

  function alpha(hex, a) {
    var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
    if (!m) { return hex; }
    return "rgba(" + parseInt(m[1], 16) + "," + parseInt(m[2], 16) + "," + parseInt(m[3], 16) + "," + a + ")";
  }

  function drawEdges() {
    ctx.lineWidth = 1;
    ctx.strokeStyle = alpha(colour.line, 0.18);
    left.concat(right).forEach(function (n) {
      ctx.beginPath();
      ctx.moveTo(n.x, n.y);
      ctx.quadraticCurveTo((n.x + hub.x) / 2, n.y, hub.x, hub.y);
      ctx.stroke();
    });
  }

  function drawNodes() {
    ctx.font = "600 11px Inter, system-ui, sans-serif";
    ctx.textBaseline = "middle";
    var showLabels = W >= 700;
    left.concat(right).forEach(function (n, i) {
      var isLeft = i < left.length;
      ctx.beginPath();
      ctx.arc(n.x, n.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = isLeft ? colour.deep : colour.accent;
      ctx.fill();
      if (showLabels) {
        ctx.fillStyle = alpha(colour.label, 0.85);
        ctx.textAlign = isLeft ? "left" : "right";
        ctx.fillText(n.label, n.x + (isLeft ? 10 : -10), n.y);
      }
    });
  }

  function drawPackets() {
    packets.forEach(function (p) {
      var cx = (p.from.x + p.to.x) / 2, cy = p.inbound ? p.from.y : p.to.y;
      var t = p.t, u = 1 - t;
      var x = u * u * p.from.x + 2 * u * t * cx + t * t * p.to.x;
      var y = u * u * p.from.y + 2 * u * t * cy + t * t * p.to.y;
      ctx.beginPath();
      ctx.arc(x, y, 2.6, 0, Math.PI * 2);
      ctx.fillStyle = p.inbound ? colour.deep : colour.accent;
      ctx.globalAlpha = Math.sin(t * Math.PI) * 0.9 + 0.1;
      ctx.fill();
      ctx.globalAlpha = 1;
    });
  }

  function frame() {
    ctx.clearRect(0, 0, W, H);
    drawEdges();
    drawPackets();
    drawNodes();
    if (!reduce) {
      if (Math.random() < 0.08 && packets.length < 26) { spawn(); }
      packets.forEach(function (p) { p.t += p.speed; });
      packets = packets.filter(function (p) { return p.t < 1; });
      window.requestAnimationFrame(frame);
    }
  }

  readColours();
  layout();
  window.addEventListener("resize", function () { layout(); if (reduce) { frame(); } });
  new MutationObserver(function () { readColours(); if (reduce) { frame(); } })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  frame();
}());
