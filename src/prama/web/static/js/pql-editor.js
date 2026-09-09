/* The PQL editor.
 *
 * CodeMirror 5 with a mode defined through simple.js, which is a list of
 * regular expressions rather than a hand-written tokeniser. That is a
 * deliberate limit: the mode's job is syntax colour, and the moment it starts
 * making judgements about validity it becomes a second implementation of the
 * parser that will disagree with the real one. Everything that decides
 * anything is answered by the server.
 *
 * Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 */
(function ($) {
  "use strict";

  var KEYWORDS = "CHECK|SUITE|ON|WHERE|BY|SEVERITY|DIMENSION|BECAUSE|EVIDENCE|" +
    "OWNER|SCHEDULE|ON FAIL|BELOW|ABOVE|BETWEEN|AND|OR|NOT|IS|NULL|IN|MATCHES|" +
    "HAS|UNIQUE|KEY|REFERENCES|UNKNOWN|COUNT|SUM|AVG|MIN|MAX|OF|EACH|FOR";

  CodeMirror.defineSimpleMode("pql", {
    start: [
      { regex: /--.*/, token: "comment" },
      { regex: /\/\*/, token: "comment", next: "comment" },
      { regex: /'(?:[^\\']|\\.)*'?/, token: "string" },
      { regex: /\/(?:[^\\\/]|\\.)*\/?/, token: "string-2" },
      { regex: new RegExp("\\b(?:" + KEYWORDS + ")\\b", "i"), token: "keyword" },
      { regex: /\b(critical|major|minor|info)\b/i, token: "atom" },
      { regex: /\b\d+(?:\.\d+)?%?\b/, token: "number" },
      { regex: /[-+\/*=<>!]+/, token: "operator" },
      { regex: /[a-zA-Z_][\w.]*/, token: "variable" }
    ],
    comment: [
      { regex: /.*?\*\//, token: "comment", next: "start" },
      { regex: /.*/, token: "comment" }
    ],
    meta: { lineComment: "--" }
  });

  window.pramaPqlStudio = function (endpoints) {
    var editor = CodeMirror.fromTextArea(document.getElementById("pql-source"), {
      mode: "pql",
      lineNumbers: true,
      lineWrapping: true,
      /* Tab inserts spaces and does NOT move focus out of the editor, which
         would trap a keyboard user. Escape then Tab leaves — the convention
         CodeMirror users expect and screen-reader users depend on. */
      extraKeys: {
        "Ctrl-Space": "autocomplete",
        Tab: function (cm) { cm.replaceSelection("  "); },
        Esc: function (cm) { cm.getInputField().blur(); }
      }
    });

    /* Completion offers only what exists: the declared dataset slugs and the
       keywords. It never invents a column name — a suggestion the estate
       cannot satisfy is worse than no suggestion, because it gets accepted. */
    CodeMirror.registerHelper("hint", "pql", function (cm) {
      var cursor = cm.getCursor();
      var line = cm.getLine(cursor.line);
      var start = cursor.ch;
      while (start && /[\w.]/.test(line.charAt(start - 1))) { start -= 1; }
      var word = line.slice(start, cursor.ch).toLowerCase();
      var candidates = (endpoints.datasets || []).concat(KEYWORDS.split("|"));
      return {
        list: candidates.filter(function (c) {
          return !word || c.toLowerCase().indexOf(word) === 0;
        }),
        from: CodeMirror.Pos(cursor.line, start),
        to: cursor
      };
    });

    function post(url, target, busyMessage) {
      var panel = $(target);
      panel.attr("aria-busy", "true").html(
        '<p class="text-muted">' + busyMessage + "</p>");
      $.post(url, { source: editor.getValue(), target: $("#target").val() })
        .done(function (html) {
          panel.html(html);
          /* Prism only highlights what was in the document when it loaded, and
             every one of these panels arrives afterwards. Without this the SQL
             renders as plain text, which reads as a rendering bug rather than
             as the missing call it is. */
          if (window.Prism) { window.Prism.highlightAllUnder(panel[0]); }
          window.pramaAnnounce($(html).text().slice(0, 200));
        })
        .fail(function (xhr) {
          /* Visibly. A studio that silently keeps the previous result after a
             failed check is telling the author their broken edit is fine. */
          panel.html('<div class="alert alert-danger mb-0">The check did not run (' +
            (xhr.status || "no response") + "). The panel below is from before " +
            "this attempt and does not describe what you have just typed.</div>");
        })
        .always(function () { panel.removeAttr("aria-busy"); });
    }

    $("#check").on("click", function () {
      post(endpoints.check, "#findings", "Checking…");
      $("#plans").empty();
      $("#preview-panel").empty();
    });
    $("#compile").on("click", function () {
      post(endpoints.compile, "#plans", "Compiling…");
    });
    $("#preview").on("click", function () {
      post(endpoints.preview, "#preview-panel", "Running it against real data…");
    });

    /* The backtest, over Server-Sent Events.
     *
     * Each day arrives as its own event and is drawn the moment it lands,
     * because thirty days is thirty round trips and a panel that shows nothing
     * for forty seconds is one people stop waiting for.
     *
     * The whole point of the display is the two counts the server keeps apart:
     * days that alerted, and days there was nothing to look at. Averaging the
     * second into the first is exactly how a backtest comes out flatter than
     * the truth, so the table shows every day and the summary states both. */
    var stream = null;

    function stop() {
      if (stream) { stream.close(); stream = null; }
    }

    function cell(trial) {
      var badge = '<span class="verdict-' + trial.verdict + ' badge">' +
        trial.verdict + "</span>";
      var counts = trial.has_data
        ? (trial.was_bounded || !trial.screen_is_complete ? "at least " : "") +
          Math.round(trial.violating_rows).toLocaleString() + " of " +
          Math.round(trial.scanned_rows).toLocaleString()
        : (trial.error
            ? '<span class="text-danger">could not be read</span>'
            : '<span class="text-muted">no rows in scope</span>');
      return "<tr><td><code>" + trial.label + "</code></td><td>" + badge +
        "</td><td>" + counts + "</td></tr>";
    }

    $("#backtest").on("click", function () {
      stop();
      var panel = $("#backtest-progress");
      var column = $("#period-column").val() || "";
      if (!column.trim()) {
        /* Refused here as well as on the server, because the server's refusal
           costs a round trip and this one names the field they are looking
           at. */
        panel.html('<div class="alert alert-warning mb-0">Name the column that ' +
          "carries the business date. Guessing it would backtest the wrong " +
          "slices and look exactly like backtesting the right ones.</div>");
        return;
      }
      var url = endpoints.backtest + "?source=" +
        encodeURIComponent(editor.getValue()) +
        "&period_column=" + encodeURIComponent(column) +
        "&days=" + encodeURIComponent($("#backtest-days").val() || "");

      panel.attr("aria-busy", "true").html(
        '<p class="text-muted" id="bt-status">Starting…</p>' +
        '<div class="table-responsive"><table class="table table-sm mb-2">' +
        "<thead><tr><th>Day</th><th>Verdict</th><th>Violating rows</th></tr></thead>" +
        '<tbody id="bt-rows"></tbody></table></div>' +
        '<div id="bt-summary"></div>');

      stream = new EventSource(url);
      var seen = 0;
      var expected = 0;

      stream.addEventListener("start", function (event) {
        expected = JSON.parse(event.data).periods;
        $("#bt-status").text("0 of " + expected + " days…");
      });

      stream.addEventListener("trial", function (event) {
        var trial = JSON.parse(event.data);
        seen += 1;
        $("#bt-rows").append(cell(trial));
        $("#bt-status").text(seen + " of " + expected + " days…");
      });

      stream.addEventListener("summary", function (event) {
        var summary = JSON.parse(event.data);
        var note = summary.is_a_lower_bound
          ? "<div class=\"uncalibrated small mt-2\">At least this many. Some days " +
            "were screened or capped, so the alert count can only be higher.</div>"
          : "";
        var thin = summary.is_trustworthy
          ? ""
          : "<div class=\"uncalibrated small mt-2\">Too few evaluated days to quote " +
            "a rate from. One noisy day dominates this answer.</div>";
        $("#bt-summary").html('<p class="mb-0">' + summary.message + "</p>" + note + thin);
        window.pramaAnnounce(summary.message);
      });

      stream.addEventListener("failed", function (event) {
        var failure = JSON.parse(event.data);
        $("#bt-summary").html('<div class="alert alert-danger mb-0"><strong>' +
          failure.message + "</strong>" +
          (failure.remedy ? '<div class="small mt-1">' + failure.remedy + "</div>" : "") +
          "</div>");
      });

      /* Both terminal paths clear the busy state and close the stream. Without
         the explicit close, EventSource reconnects on its own and silently
         re-runs the whole backtest — which on a warehouse is real money spent
         on an answer already on the screen. */
      stream.addEventListener("done", function () {
        $("#bt-status").text(seen + " of " + expected + " days");
        panel.removeAttr("aria-busy");
        stop();
      });

      stream.onerror = function () {
        /* A dropped connection is not an empty result. Saying so is the whole
           difference between a backtest that found nothing and one that never
           finished looking. */
        if (!stream) { return; }
        $("#bt-summary").html('<div class="alert alert-warning mb-0">The stream ' +
          "stopped after " + seen + " of " + expected + " days. What is above is " +
          "what was measured; it is not a result for the whole period.</div>");
        panel.removeAttr("aria-busy");
        stop();
      };
    });
  };
})(jQuery);
