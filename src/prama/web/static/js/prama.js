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
      var bases = window.pramaThemeBases || {};
      document.documentElement.setAttribute("data-bs-theme", bases[value] || "light");
    }
    try { STORE.setItem("prama:" + attribute, value); } catch (e) { /* private mode */ }
    /* A cookie as well as local storage, because the *server* renders the
       theme into the markup — that is what stops the page flashing light and
       being repainted. Local storage cannot be read server-side; a cookie can.
       SameSite=Lax and a year, since this is a display preference and nothing
       more. */
    var name = attribute === "data-theme" ? "prama_theme" : "prama_density";
    document.cookie = name + "=" + encodeURIComponent(value) +
      ";path=/;max-age=31536000;samesite=lax";
  }

  $(function () {
    /* The server has already rendered the stored preference into <html>. This
       only re-applies what local storage holds when there is no cookie yet —
       a first visit after the cookie was cleared — and never fights the
       server-rendered value on an ordinary load. */
    if (document.cookie.indexOf("prama_theme=") < 0) {
      ["data-theme", "data-density"].forEach(function (attribute) {
        var saved = null;
        try { saved = STORE.getItem("prama:" + attribute); } catch (e) { saved = null; }
        if (saved) { applyPreference(attribute, saved); }
      });
    }

    /* The theme picker. The Bootstrap base for each theme comes from the
       server rather than being re-derived here: a second opinion about whether
       "green" is a light theme would show up as one unreadable dropdown on
       one page, which is the hardest kind of bug to find. */
    var bases = window.pramaThemeBases || {};
    $("[data-theme-choice]").on("click", function () {
      var chosen = $(this).data("themeChoice");
      document.documentElement.setAttribute("data-bs-theme", bases[chosen] || "light");
      applyPreference("data-theme", chosen);
      $("[data-theme-choice]").attr("aria-checked", "false");
      $(this).attr("aria-checked", "true");
      announce($.trim($(this).text()) + " theme");
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

// "About this page": collapsed once, it stays collapsed in this browser; the ?
// in the header opens it, brings it into view and shows where it is.
(function () {
  var box = document.getElementById("page-help");
  if (!box) { return; }
  try { if (window.localStorage.getItem("prama.pageHelp") === "closed") { box.open = false; } } catch (e) { /* private window */ }
  box.addEventListener("toggle", function () {
    try { window.localStorage.setItem("prama.pageHelp", box.open ? "open" : "closed"); } catch (e) { /* private window */ }
  });
  document.querySelectorAll("[data-page-help]").forEach(function (link) {
    link.addEventListener("click", function (ev) {
      ev.preventDefault();
      box.open = true;
      box.scrollIntoView({ behavior: "smooth", block: "start" });
      box.classList.remove("ph-flash"); void box.offsetWidth; box.classList.add("ph-flash");
    });
  });
})();
