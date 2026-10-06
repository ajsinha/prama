"""axe-core, in a real browser, on every page of the console.

``test_accessibility.py`` is the floor: contrast arithmetic and HTML structure,
both checked without a DOM. This is the ceiling, and it catches three classes of
failure that static analysis structurally cannot:

* **Computed contrast.** A colour is legible or not only after the cascade has
  run. A token that passes in the palette can fail on the page because something
  inherited a background, and the arithmetic tests cannot see it.
* **ARIA validity.** A ``role`` that does not exist, a ``aria-labelledby``
  pointing at nothing, a required child missing from a composite widget. Every
  one of these parses fine and is announced as nothing.
* **Focus order and interactivity.** Whether a control can be reached, in an
  order that matches the reading order.

Two decisions worth stating.

**The browser is the one already installed.** Playwright drives Chrome through
``channel="chrome"`` rather than downloading its own, because an accessibility
suite that costs a 150MB download on every clone is one that gets disabled.

**A skip is loud.** An audit that quietly does not run and reports green is
worse than no audit: the badge says accessible and nobody has looked. Missing
playwright or missing Chrome produces a skip whose reason says exactly that, and
``test_the_audit_actually_ran`` fails rather than skips when the vendored
axe-core is absent — because that one is a repository problem, not an
environment one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.web.conftest import live_console

from prama.report.themes import BASES
from prama.report.themes import THEMES as _THEMES

#: Each theme's page ground, to wait for before measuring anything on it.
BODY = {theme.name: theme.body for theme in _THEMES}

#: `bypass_csp=True` on every page here. The console now sends a
#: Content-Security-Policy with a per-response nonce (QA finding UI-045), and
#: `page.add_script_tag` is precisely what such a policy exists to block — so
#: axe-core could not be injected and all 24 checks failed at once.
#:
#: Bypassing is right for *these* tests and only these: they ask whether the
#: rendered page is usable, not whether the header is present. The header has
#: its own test, which asserts the policy is sent and does not bypass it. A
#: suite that turned the policy off everywhere would have removed the evidence
#: that it is on.
AXE = Path(__file__).parent / "vendor" / "axe.min.js"

#: WCAG 2.2 AA. Best-practice rules are excluded deliberately: they are
#: opinions, several of them contradict Bootstrap's own markup, and a suite that
#: fails on an opinion is one somebody switches off along with the conformance
#: rules it was protecting.
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

PAGES = (
    "/estate",
    "/estate/gaps",
    "/declarations",
    "/declarations/new",
    "/relationships",
    "/relationships/new",
    "/controls",
    "/controls/studio",
    "/controls/build",
    "/proposals",
    "/evidence",
    "/reports",
    "/incidents",
    "/reconciliation",
    "/scorecards",
    "/attestations",
)

#: Every theme the picker offers, derived rather than listed: a hand-kept list
#: silently stopped covering the sixth theme the day it was added. Computed
#: contrast is a property of the rendered page, so a palette that passes the
#: arithmetic in every theme still has to be looked at in every theme.
THEMES = tuple(theme.name for theme in _THEMES)


def _playwright():
    return pytest.importorskip(
        "playwright.sync_api",
        reason=(
            "playwright is not installed, so the accessibility audit did NOT run. "
            "`pip install playwright` — it drives the Chrome already on this "
            "machine and downloads no browser."
        ),
    )


@pytest.fixture(scope="module")
def server(tmp_path_factory) -> Iterator[str]:
    """The real application on a real port (tests/web/conftest.py, ``live_console``).

    A live server rather than an ASGI transport: axe runs inside a browser, and
    a browser needs a URL. Started once for the module, because the audit visits
    eighty pages and a per-test server would dominate the runtime.
    """
    yield from live_console(tmp_path_factory.mktemp("axe"))


@pytest.fixture(scope="module")
def browser(server: str):
    sync_api = _playwright()
    with sync_api.sync_playwright() as playwright:
        try:
            # The Chrome already installed, rather than a downloaded one: an
            # audit that costs a 150MB download per clone gets disabled.
            launched = playwright.chromium.launch(channel="chrome")
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"no Chrome to drive, so the accessibility audit did NOT run: {exc}")
        yield launched
        launched.close()


def _violations(browser, base: str, path: str, theme: str) -> list[dict]:
    # Reduced motion, which the stylesheet already honours by collapsing every
    # transition to .01ms. Without it, switching the theme starts Bootstrap's
    # 150ms colour transition and axe samples a frame *part way through it*:
    # the dark link came back as #5c6fc9, which is the midpoint between the
    # light and dark values and a colour the page never rests at. Auditing in
    # the mode a motion-sensitive reader browses in is also the mode worth
    # auditing.
    page = browser.new_page(reduced_motion="reduce", bypass_csp=True)
    try:
        page.goto(f"{base}{path}", wait_until="networkidle")
        # BOTH attributes, exactly as the switcher sets them. Flipping
        # `data-theme` alone leaves `data-bs-theme` on the base the server
        # rendered, so a dark theme paints Prama's dark tokens over Bootstrap's
        # light ones — a mismatch no reader can reach, and one that reports
        # contrast failures nobody has. That is what made this suite fail on
        # `dark`, the theme whose base actually differs.
        page.evaluate(
            """([theme, base]) => {
                document.documentElement.setAttribute('data-theme', theme);
                document.documentElement.setAttribute('data-bs-theme', base);
            }""",
            [theme, BASES[theme]],
        )
        # Wait for the theme to have actually taken effect, rather than assume
        # setting the attribute repaints synchronously. Under load the page was
        # occasionally measured before the new palette applied, which produced a
        # contrast reading for a theme that was not on screen. Tied to the exact
        # colour being waited for, so it cannot pass early.
        page.wait_for_function(
            """expected => {
                const seen = getComputedStyle(document.body).backgroundColor;
                const [r, g, b] = seen.match(/\\d+/g).map(Number);
                const hex = '#' + [r, g, b]
                    .map(v => v.toString(16).padStart(2, '0')).join('').toUpperCase();
                return hex === expected.toUpperCase();
            }""",
            arg=BODY[theme],
            timeout=5000,
        )
        page.add_script_tag(path=str(AXE))
        result = page.evaluate(
            "async tags => await axe.run(document, {runOnly: {type: 'tag', values: tags}})",
            TAGS,
        )
        return list(result.get("violations") or [])
    finally:
        page.close()


def _describe(violations: list[dict], path: str, theme: str) -> str:
    """A failure message somebody can act on without opening a browser."""
    lines = [f"{path} in the {theme} theme: {len(violations)} violation(s)"]
    for violation in violations:
        lines.append(f"  [{violation['impact']}] {violation['id']}: {violation['help']}")
        for node in violation.get("nodes", [])[:3]:
            lines.append(f"      {''.join(node.get('target', []))}")
            summary = (node.get("failureSummary") or "").replace("\n", " ")
            lines.append(f"      {summary[:200]}")
        lines.append(f"      {violation['helpUrl']}")
    return "\n".join(lines)


class TestTheAuditItself:
    def test_axe_core_is_vendored(self) -> None:
        """A repository problem, not an environment one, so it fails rather
        than skips. A suite that silently has no analyser to run reports green
        and nobody has looked."""
        assert AXE.exists(), (
            "tests/web/vendor/axe.min.js is missing. Without it nothing is "
            "audited and the rest of this file would skip quietly."
        )
        assert AXE.stat().st_size > 100_000

    def test_it_finds_a_violation_when_there_is_one(self, browser, server: str) -> None:
        """The counterfactual. An audit that passes everything is
        indistinguishable from an audit that is not running, and this is the
        only test that tells them apart."""
        page = browser.new_page(bypass_csp=True)
        try:
            page.set_content(
                "<html lang='en'><body><img src='x.png'><input type='text'></body></html>"
            )
            page.add_script_tag(path=str(AXE))
            result = page.evaluate(
                "async tags => await axe.run(document, {runOnly: {type: 'tag', values: tags}})",
                TAGS,
            )
            found = {v["id"] for v in result["violations"]}
        finally:
            page.close()
        assert "image-alt" in found
        assert found, "axe reported nothing on deliberately broken markup"


@pytest.mark.parametrize("path", PAGES)
def test_no_violations_in_the_default_theme(browser, server: str, path: str) -> None:
    violations = _violations(browser, server, path, "light")
    assert not violations, _describe(violations, path, "light")


@pytest.mark.parametrize("theme", THEMES)
def test_every_theme_is_clean_on_the_densest_page(browser, server: str, theme: str) -> None:
    """The estate map carries the most colour of any screen — dimension chips,
    verdict marks, brand accents — so it is where a theme's computed contrast
    fails first."""
    violations = _violations(browser, server, "/estate", theme)
    assert not violations, _describe(violations, "/estate", theme)


@pytest.mark.parametrize("theme", ("dark",))
def test_the_dark_themes_are_clean_on_a_form(browser, server: str, theme: str) -> None:
    """Forms are where a dark theme most often fails: an input that inherits a
    light background from a component library, with dark text on it, passes
    every arithmetic check on the tokens and is unreadable on the page."""
    violations = _violations(browser, server, "/declarations/new", theme)
    assert not violations, _describe(violations, "/declarations/new", theme)


def test_the_json_report_is_written(browser, server: str, tmp_path: Path) -> None:
    """Somebody has to be able to read the audit without running it.

    Written to a temporary path rather than the repository: a report checked in
    is a report that goes stale, and a stale accessibility report is read as a
    current one.
    """
    page = browser.new_page(reduced_motion="reduce", bypass_csp=True)
    try:
        page.goto(f"{server}/estate", wait_until="networkidle")
        page.add_script_tag(path=str(AXE))
        result = page.evaluate(
            "async tags => await axe.run(document, {runOnly: {type: 'tag', values: tags}})",
            TAGS,
        )
    finally:
        page.close()
    report = tmp_path / "axe.json"
    report.write_text(json.dumps(result, indent=2))
    loaded = json.loads(report.read_text())
    assert loaded["violations"] == []
    # Passes are recorded too. "Nothing failed" and "forty rules ran and
    # nothing failed" are different claims and only the second is evidence.
    assert len(loaded["passes"]) > 5
