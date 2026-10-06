"""Every console page fits a phone: nothing makes the page scroll sideways at 390px.

Measured before this existed, with the case studies' data in the console: nine of
forty-three pages scrolled sideways on a phone. Wide tables stretched the page and
pushed the menu button off the screen; screen-reader labels inside table cells,
absolutely positioned, escaped the table's scrolling box and widened the page
anyway; the public header never collapsed, so "Sign in" was cut off; and the break
workbench's two columns of amounts were wider than the screen.

A table may scroll inside its own box: that is how a wide table is read on a phone.
The page may not. Seeded with controls whose PQL is long, because an empty table
cannot overflow anything.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from tests.web.conftest import live_console
from tests.web.test_axe import _playwright

from prama.web import page_help

PHONE = {"width": 390, "height": 844}

#: Every page "About this page" knows (so every console page) without a {parameter}.
PAGES = sorted(p for p in page_help.PAGES if "{" not in p)

#: Pages this single-tenant, nobody-signed-in server cannot show, and why.
NOT_HERE = {
    "/sign-in": "redirects to the console when an estate is the default",
}

#: How wide the page actually lays out, against the screen it is on.
MEASURE = """() => ({
  screen: document.documentElement.clientWidth,
  page: document.documentElement.scrollWidth,
})"""


async def _seed(uow: Any, tenant_id: str) -> None:
    """Controls with long PQL: the widest thing a console table shows."""
    for i, pql in enumerate(
        (
            "CHECK counterparties HAS UNIQUE KEY (lei) SEVERITY critical DIMENSION uniqueness",
            "CHECK trades.notional_in_reporting_currency IS NOT NULL SEVERITY major "
            "DIMENSION completeness",
            "CHECK settlement_instructions.beneficiary_account_identifier MATCHES "
            "/^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/ SEVERITY critical DIMENSION validity",
        )
    ):
        control, _ = await uow.controls.declare(
            tenant_id=tenant_id,
            identity=f"mobile-{i}",
            pql=pql,
            status="proposed",
            criticality=3,
            reason="seeded for the phone-width test",
        )
        await uow.controls.activate(
            str(control.id), tenant_id=tenant_id, approved_by="seed", reason="seeded"
        )


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    yield from live_console(tmp_path_factory.mktemp("mobile"), seed=_seed)


@pytest.fixture(scope="module")
def phone(server: str) -> Iterator[Any]:
    sync_api = _playwright()
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome")
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"no Chrome to drive, so the phone-width check did NOT run: {exc}")
        context = browser.new_context(viewport=PHONE, bypass_csp=True)
        yield context.new_page()
        browser.close()


def test_there_are_pages_to_check() -> None:
    assert len(PAGES) > 35


@pytest.mark.parametrize("path", [p for p in PAGES if p not in NOT_HERE])
def test_the_page_fits_a_phone(phone: Any, server: str, path: str) -> None:
    response = phone.goto(server + path)
    assert response is not None and response.ok, f"{path}: {response and response.status}"
    phone.wait_for_load_state("networkidle")
    width = phone.evaluate(MEASURE)
    assert width["page"] <= width["screen"], (
        f"{path} lays out {width['page']}px wide on a {width['screen']}px screen: "
        "something forces the page wider than a phone"
    )


def test_the_seeded_controls_are_on_the_page(phone: Any, server: str) -> None:
    """So the controls page above was measured with its long PQL, not empty."""
    phone.goto(server + "/controls")
    assert "beneficiary_account_identifier" in phone.content()


def test_the_public_header_folds_into_a_menu(phone: Any, server: str) -> None:
    phone.goto(server + "/about")
    toggle = phone.locator('[data-bs-target="#nav-public"]')
    assert toggle.is_visible()
    help_link = phone.locator("#nav-public .nav-link").first
    assert not help_link.is_visible()
    toggle.click()
    help_link.wait_for(state="visible")
