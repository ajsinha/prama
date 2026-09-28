"""The layer every template sits on.

Jinja needs three things from the application that FastAPI does not give it:
a way to name a route rather than hard-code its path, a place for one-shot
messages that survive a redirect, and the navigation state. This module is all
three, and it is deliberately the same shape as DishtaYantra's
``web/fastapi_compat`` so a template moves between the two unchanged.

One difference, on purpose: the templates directory is resolved from the
package, not from the working directory. A UI that renders when started from
the repository root and 500s when started from anywhere else is a defect that
only shows up in the deployment nobody tested.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from prama.core.log import get_logger
from prama.report.themes import BASES, THEMES
from prama.version import PRODUCT_TAGLINE, VERSION

_log = get_logger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"

#: The message categories a template knows how to style. A category outside
#: this set renders as ``info`` rather than as an unstyled bare string, so a
#: typo degrades to a visible message instead of an invisible one.
CATEGORIES = ("success", "info", "warning", "error")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@dataclasses.dataclass(frozen=True, slots=True)
class NavItem:
    """One entry in the primary navigation.

    ``prefix`` rather than an exact path, because /controls/abc must still light
    the Controls tab: a user who has drilled three levels down and can no longer
    see where they are is the commonest way a console feels like a maze.
    """

    label: str
    endpoint: str
    prefix: str
    icon: str = ""

    def active_for(self, path: str) -> bool:
        return path == self.prefix or path.startswith(self.prefix.rstrip("/") + "/")


#: Order is the reading order of the work: see the estate, say what it means,
#: state the controls, look at what broke, agree the numbers, report.
NAVIGATION: tuple[NavItem, ...] = (
    NavItem("Estate", "estate_map", "/estate", "bi-diagram-3"),
    NavItem("Declarations", "declaration_list", "/declarations", "bi-journal-text"),
    NavItem("Relationships", "relationship_list", "/relationships", "bi-share"),
    NavItem("Glossary", "glossary", "/glossary", "bi-book-half"),
    NavItem("Lineage", "lineage", "/lineage", "bi-bezier2"),
    NavItem("Controls", "control_list", "/controls", "bi-shield-check"),
    NavItem("Proposals", "proposal_queue", "/proposals", "bi-lightbulb"),
    NavItem("Incidents", "incident_list", "/incidents", "bi-exclamation-triangle"),
    NavItem("Reconciliation", "reconciliation_list", "/reconciliation", "bi-arrow-left-right"),
    NavItem("Scorecards", "scorecard_list", "/scorecards", "bi-clipboard-data"),
    NavItem("Evidence", "evidence_chain", "/evidence", "bi-shield-check"),
    NavItem("Attestations", "attestation_list", "/attestations", "bi-pen"),
    NavItem("Reports", "report_index", "/reports", "bi-file-earmark-pdf"),
)


#: The navigation on the public pages, after Maya's `_nav_public.html`.
PUBLIC_NAVIGATION: tuple[tuple[str, str, str, str], ...] = (
    ("Help", "help_index", "/help", "bi-question-circle"),
    ("About", "about", "/about", "bi-info-circle"),
)


def url_for(request: Request, name: str, **params: Any) -> str:
    """Resolve a route name to a URL, with Flask's semantics.

    ``url_for('static', filename='css/prama.css')`` hits the mounted static
    app; anything matching a path parameter is substituted; whatever is left
    becomes the query string.
    """
    app = request.app
    if name == "static":
        filename = params.pop("filename", "")
        url = app.url_path_for("static", path=filename)
        return f"{url}?{urlencode(params)}" if params else url

    path_params: set[str] = set()
    for route in app.routes:
        if getattr(route, "name", None) == name:
            path_params = set(getattr(route, "param_convertors", {}))
            break
    in_path = {k: v for k, v in params.items() if k in path_params}
    in_query = {k: v for k, v in params.items() if k not in path_params}
    url = app.url_path_for(name, **in_path)
    return f"{url}?{urlencode(in_query)}" if in_query else url


def _preference(request: Request, cookie: str, allowed: tuple[str, ...]) -> str:
    """A display preference from a cookie, validated against a closed set.

    Validated, always. The value is written into an HTML attribute, and a
    cookie is user-supplied — an unchecked one is an attribute injection with
    extra steps. An unknown value falls back to the first permitted rather than
    raising: a stale cookie from an older build should render the default page,
    not an error.
    """
    value = request.cookies.get(cookie, "")
    return value if value in allowed else allowed[0]


def chosen_theme(request: Request) -> str:
    """Which theme to render, before any JavaScript runs.

    Server-side because the alternative flashes. A page that renders light and
    is repainted by a script on load is unpleasant on every theme and genuinely
    unusable on the amber-on-black one, where the flash is a white screen.

    ``?theme=`` overrides the cookie, so a theme can be linked and previewed
    without changing anybody's preference.
    """
    names = tuple(theme.name for theme in THEMES)
    preview = request.query_params.get("theme", "")
    if preview in names:
        return preview
    return _preference(request, "prama_theme", names)


def flash(request: Request, message: str, category: str = "success") -> None:
    """Queue a message for the next rendered page."""
    if category not in CATEGORIES:
        _log.warning("unknown flash category %r, showing as info", category)
        category = "info"
    request.session.setdefault("_flashes", []).append([category, message])


def get_flashed_messages(request: Request, *, with_categories: bool = False) -> list[Any]:
    """Drain the queue. Reading consumes, as Flask does."""
    flashes = request.session.pop("_flashes", [])
    if with_categories:
        return [(category, message) for category, message in flashes]
    return [message for _, message in flashes]


def render(request: Request, template: str, status_code: int = 200, **context: Any) -> Any:
    """Render a template with the shell's context already supplied."""
    path = request.url.path
    context.setdefault(
        "nav",
        [
            {
                "label": item.label,
                "href": url_for(request, item.endpoint),
                "icon": item.icon,
                "active": item.active_for(path),
            }
            for item in NAVIGATION
        ],
    )
    context.setdefault("public_nav", False)
    context.setdefault(
        "public_links",
        [
            {
                "label": label,
                "href": url_for(request, endpoint),
                "icon": icon,
                "active": path == prefix or path.startswith(prefix + "/"),
            }
            for label, endpoint, prefix, icon in PUBLIC_NAVIGATION
        ],
    )
    context.setdefault("theme", chosen_theme(request))
    context.setdefault("density", _preference(request, "prama_density", ("comfortable", "compact")))
    context.setdefault(
        "themes",
        [{"name": t.name, "label": t.label, "note": t.note, "header": t.header} for t in THEMES],
    )
    context.setdefault("app_version", VERSION)
    context.setdefault("app_tagline", PRODUCT_TAGLINE)
    # Who is signed in, for the shell. The sign-out control needs to know
    # whether there is a session to end, and the template had no way to ask:
    # `caller` is a route dependency and never reached the context, so a
    # `{% if caller %}` in the shell would have been permanently false — the
    # same defect as having no control at all, wearing a fix (QA finding
    # UI-023).
    session = getattr(request, "session", {}) or {}
    context.setdefault(
        "signed_in",
        {
            "username": session.get("username", ""),
            "display_name": session.get("display_name", ""),
            # For the menu only. Every admin page is guarded by its own scope
            # check; hiding a link is courtesy, not control.
            "is_admin": bool({"admin", "*"} & set(session.get("scopes", []))),
        }
        if session.get("principal_id")
        else None,
    )
    return templates.TemplateResponse(
        request=request, name=template, context=context, status_code=status_code
    )


def redirect_to(
    request: Request,
    endpoint: str,
    *,
    flash_message: str | None = None,
    flash_category: str = "success",
    **params: Any,
) -> RedirectResponse:
    """Redirect to a named route. 303, so a POST handler lands on a GET."""
    if flash_message:
        flash(request, flash_message, flash_category)
    return RedirectResponse(url=url_for(request, endpoint, **params), status_code=303)


def flash_error_and_log(request: Request, user_message: str, exc: Exception) -> None:
    """Show the failure and record it in full.

    Both, always. A flash without a log leaves nothing to diagnose from; a log
    without a flash leaves the user staring at a page that silently did nothing.
    """
    _log.exception("%s", user_message, exc_info=exc)
    flash(request, f"{user_message}: {exc}", "error")


def _rate(value: float | None, decimals: int = 1) -> Any:
    """A rate as a percentage that never rounds towards good news."""
    from markupsafe import Markup

    from prama.report.rate import percent

    if value is None:
        # Not "0%". An unmeasured rate and a measured zero are opposite facts.
        return Markup("&mdash;")
    return Markup(percent(float(value), decimals=decimals))


def install_globals() -> None:
    """Make the helpers callable from inside a template.

    ``url_for`` and ``get_flashed_messages`` are declared as context functions
    so Jinja passes the request through automatically and a template writes
    ``url_for('estate_map')`` — the form every template in DishtaYantra already
    uses.
    """
    import jinja2

    @jinja2.pass_context
    def _csp_nonce(context: Any) -> str:
        """The nonce this response's Content-Security-Policy will name.

        Read from request state rather than generated here, so the value in the
        attribute and the value in the header are the same one. Generating it
        in the template would produce a nonce the policy does not list, which
        blocks the script just as thoroughly as having none.
        """
        request = context.get("request")
        return str(getattr(getattr(request, "state", None), "csp_nonce", "") or "")

    @jinja2.pass_context
    def _url_for(context: Any, name: str, **params: Any) -> str:
        return url_for(context["request"], name, **params)

    @jinja2.pass_context
    def _flashed(context: Any, with_categories: bool = False) -> list[Any]:
        return get_flashed_messages(context["request"], with_categories=with_categories)

    # A filter rather than a helper each template remembers to call: the one
    # place a percentage is formatted, so no screen can round a real defect
    # away by using the wrong one.
    templates.env.filters["rate"] = _rate

    templates.env.globals["csp_nonce"] = _csp_nonce

    templates.env.globals["url_for"] = _url_for
    templates.env.globals["get_flashed_messages"] = _flashed
    templates.env.globals["app_version"] = VERSION
    # The switcher needs to know which Bootstrap base each theme sits on, and
    # it is one mapping rather than a rule the JavaScript re-derives — a second
    # opinion about whether "maya-crimson" is a light theme would show up as one
    # unreadable dropdown.
    templates.env.globals["theme_bases"] = BASES
    templates.env.globals["app_tagline"] = PRODUCT_TAGLINE
