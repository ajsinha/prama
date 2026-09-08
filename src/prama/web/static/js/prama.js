/* Prama's shell behaviour. jQuery, as DishtaYantra does it.
 *
 * Deliberately small. Everything that can be rendered on the server is
 * rendered on the server, and what is left here is the part that genuinely
 * cannot be: theme and density preference, partial refreshes, and announcing
 * asynchronous changes to a screen reader.
 *
 * Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 */
(function ($) {
  "use strict";

  var STORE = window.localStorage;

  /* Announce a change that happened without a page load. A screen-reader user
     who submits a form and hears nothing has, from their point of view, an
     app that did not respond. */
  function announce(message) {
    var region = document.getElementById("announcer");
    if (!region) { return; }
    region.textContent = "";
    window.setTimeout(function () { region.textContent = message; }, 60);
  }
  window.pramaAnnounce = announce;

  function applyPreference(attribute, value) {
    document.documentElement.setAttribute(attribute, value);
    if (attribute === "data-theme") {
      document.documentElement.setAttribute("data-bs-theme", value);
    }
    try { STORE.setItem("prama:" + attribute, value); } catch (e) { /* private mode */ }
  }

  $(function () {
    ["data-theme", "data-density"].forEach(function (attribute) {
      var saved = null;
      try { saved = STORE.getItem("prama:" + attribute); } catch (e) { saved = null; }
      if (saved) { applyPreference(attribute, saved); }
    });

    $("#theme-toggle").on("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark"
        ? "light" : "dark";
      applyPreference("data-theme", next);
      announce(next === "dark" ? "Dark theme" : "Light theme");
    });

    $("#density-toggle").on("click", function () {
      var next = document.documentElement.getAttribute("data-density") === "compact"
        ? "comfortable" : "compact";
      applyPreference("data-density", next);
      announce(next === "compact" ? "Compact rows" : "Comfortable rows");
    });

    /* Partial refresh. A link or button carrying data-refresh replaces the
       named container with the fragment the server returns — the same job
       HTMX does, in the twelve lines it actually takes with jQuery already
       loaded. */
    $(document).on("click", "[data-refresh]", function (event) {
      event.preventDefault();
      var trigger = $(this);
      var target = $(trigger.data("target"));
      target.attr("aria-busy", "true");
      $.get(trigger.data("refresh"))
        .done(function (html) {
          target.html(html);
          announce(trigger.data("announce") || "Updated");
        })
        .fail(function (xhr) {
          /* Failing visibly. A panel that silently keeps showing stale data
             is worse than an error, because the reader believes it. */
          target.html(
            '<div class="alert alert-warning mb-0">Could not refresh: ' +
            (xhr.status || "no response") + ". The data shown is from before " +
            "this attempt.</div>"
          );
          announce("Refresh failed");
        })
        .always(function () { target.removeAttr("aria-busy"); });
    });
  });
})(jQuery);
