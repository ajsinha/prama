/* help.js — live filtering of the help centre's topic cards (after Maya).
 * Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. */
(function () {
  "use strict";
  var box = document.querySelector("[data-help-search]");
  if (!box) { return; }
  box.addEventListener("input", function () {
    var q = box.value.trim().toLowerCase();
    document.querySelectorAll("[data-help-section]").forEach(function (section) {
      var shown = 0;
      section.querySelectorAll("[data-help-text]").forEach(function (card) {
        var hit = !q || card.getAttribute("data-help-text").indexOf(q) >= 0;
        card.hidden = !hit;
        if (hit) { shown += 1; }
      });
      section.hidden = shown === 0;
    });
  });
}());
