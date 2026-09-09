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
    });
    $("#compile").on("click", function () {
      post(endpoints.compile, "#plans", "Compiling…");
    });
  };
})(jQuery);
