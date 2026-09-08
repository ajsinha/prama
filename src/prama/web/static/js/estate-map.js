/* The estate map.
 *
 * Sigma on WebGL, because the estates this is built for run to thousands of
 * datasets and an SVG renderer stops being usable somewhere around eight
 * hundred. Layout is a plain circular seed plus a few hundred ForceAtlas-style
 * iterations run once and then frozen: a graph that keeps drifting under the
 * cursor is impossible to point at, and pointing at things is the entire
 * interaction.
 *
 * Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 */
(function ($) {
  "use strict";

  /* Criticality, in the brand palette. Tier 1 is the most critical, which is
     the opposite of what the number suggests, so the legend and the table both
     always carry the word as well as the hue. */
  var TIER_COLOUR = {
    1: "#D9534F",
    2: "#E8823A",
    3: "#2B3FA8",
    4: "#8A93AD"
  };

  function seedPositions(graph) {
    /* A circle, then relax. Random seeding produces a different picture on
       every reload, and a map that rearranges itself between visits cannot be
       learned. */
    var n = graph.order, i = 0;
    graph.forEachNode(function (node) {
      var angle = (2 * Math.PI * i) / Math.max(n, 1);
      graph.setNodeAttribute(node, "x", Math.cos(angle) * 100);
      graph.setNodeAttribute(node, "y", Math.sin(angle) * 100);
      i += 1;
    });
  }

  function relax(graph, iterations) {
    /* Barnes-Hut would be the right answer above a few thousand nodes; this is
       the honest simple version, capped so the page cannot hang. When the cap
       binds the layout is merely less pretty, never wrong — every node still
       renders and every edge still connects the right pair. */
    var nodes = graph.nodes();
    if (nodes.length > 1500) { iterations = Math.min(iterations, 60); }
    for (var step = 0; step < iterations; step++) {
      var dx = {}, dy = {};
      nodes.forEach(function (a) { dx[a] = 0; dy[a] = 0; });
      for (var i = 0; i < nodes.length; i++) {
        for (var j = i + 1; j < nodes.length; j++) {
          var a = nodes[i], b = nodes[j];
          var ax = graph.getNodeAttribute(a, "x"), ay = graph.getNodeAttribute(a, "y");
          var bx = graph.getNodeAttribute(b, "x"), by = graph.getNodeAttribute(b, "y");
          var vx = ax - bx, vy = ay - by;
          var d2 = vx * vx + vy * vy || 0.01;
          var force = 400 / d2;
          dx[a] += vx * force; dy[a] += vy * force;
          dx[b] -= vx * force; dy[b] -= vy * force;
        }
      }
      graph.forEachEdge(function (edge, attrs, source, target) {
        var sx = graph.getNodeAttribute(source, "x"), sy = graph.getNodeAttribute(source, "y");
        var tx = graph.getNodeAttribute(target, "x"), ty = graph.getNodeAttribute(target, "y");
        var vx = (tx - sx) * 0.01, vy = (ty - sy) * 0.01;
        dx[source] += vx; dy[source] += vy;
        dx[target] -= vx; dy[target] -= vy;
      });
      nodes.forEach(function (node) {
        graph.setNodeAttribute(node, "x", graph.getNodeAttribute(node, "x") + Math.max(-10, Math.min(10, dx[node])));
        graph.setNodeAttribute(node, "y", graph.getNodeAttribute(node, "y") + Math.max(-10, Math.min(10, dy[node])));
      });
    }
  }

  function fillTable(payload, detailTemplate) {
    var rows = payload.nodes.map(function (node) {
      var a = node.attributes;
      var href = detailTemplate.replace("__ID__", encodeURIComponent(node.key));
      var state = a.bound ? (a.complete ? "Declared" : "Incomplete") : "Not connected";
      return "<tr><td><a href=\"" + href + "\">" + $("<div>").text(a.label).html() +
        "</a></td><td>" + $("<div>").text(a.shape).html() +
        "</td><td>Tier " + a.tier + "</td><td>" + state + "</td></tr>";
    });
    $("#map-rows").html(rows.join("") ||
      "<tr><td colspan=\"4\" class=\"text-muted\">Nothing declared yet.</td></tr>");
  }

  window.pramaEstateMap = function (graphUrl, detailTemplate) {
    $.getJSON(graphUrl)
      .done(function (payload) {
        fillTable(payload, detailTemplate);

        var graph = new graphology.Graph({ multi: true });
        payload.nodes.forEach(function (node) {
          graph.addNode(node.key, $.extend({}, node.attributes, {
            color: node.attributes.bound
              ? TIER_COLOUR[node.attributes.tier]
              /* Unverified Grey, and only here: a dataset nobody has connected
                 has not been examined, which is a different thing from being
                 healthy and must never look like it. */
              : "#8A93AD",
            size: Math.max(3, node.attributes.size || 4)
          }));
        });
        payload.edges.forEach(function (edge) {
          if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) { return; }
          graph.addEdgeWithKey(edge.key, edge.source, edge.target, {
            size: edge.attributes.status === "proposed" ? 0.5 : 1.5,
            color: edge.attributes.status === "proposed" ? "#8A93AD" : "#5A6480",
            type: edge.attributes.style === "dashed" ? "line" : "line"
          });
        });

        seedPositions(graph);
        relax(graph, 200);

        var renderer = new Sigma(graph, document.getElementById("estate-map"), {
          renderEdgeLabels: false,
          defaultEdgeType: "line",
          labelDensity: 0.4
        });

        renderer.on("clickNode", function (event) {
          window.location.href = detailTemplate.replace("__ID__", encodeURIComponent(event.node));
        });

        var message = payload.nodes.length + " datasets, " + payload.edges.length +
          " relationships";
        if (payload.dangling_edges) {
          /* Said out loud. A relationship whose counterparty has been retired is
             a real finding, and silently dropping it from the picture is how a
             map starts lying by omission. */
          message += ". " + payload.dangling_edges +
            " relationship(s) point at a dataset that is no longer declared and are not drawn.";
        }
        $("#map-status").text(message);
        window.pramaAnnounce(message);

        $("#map-search").on("input", function () {
          var needle = $(this).val().toLowerCase();
          graph.forEachNode(function (node, attrs) {
            var hit = !needle || (attrs.label || "").toLowerCase().indexOf(needle) >= 0;
            graph.setNodeAttribute(node, "hidden", !hit);
          });
          renderer.refresh();
        });

        $("[data-highlight]").on("click", function () {
          var mode = $(this).data("highlight");
          $("[data-highlight]").removeClass("active");
          $(this).addClass("active");
          graph.forEachNode(function (node, attrs) {
            var hit = mode === "none" ||
              (mode === "unbound" && !attrs.bound) ||
              (mode === "incomplete" && !attrs.complete);
            graph.setNodeAttribute(node, "hidden", !hit);
          });
          renderer.refresh();
        });
      })
      .fail(function (xhr) {
        $("#map-status")
          .addClass("text-danger")
          .text("The estate could not be loaded (" + (xhr.status || "no response") +
                "). The list below is empty because nothing was received, not " +
                "because nothing is declared.");
        $("#map-rows").html("<tr><td colspan=\"4\" class=\"text-danger\">Not loaded.</td></tr>");
      });
  };
})(jQuery);
