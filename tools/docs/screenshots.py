"""
Real screenshots of the console, for the architecture and developer guides.

    python tools/docs/screenshots.py              # every shot, into docs/assets/screenshots/
    python tools/docs/screenshots.py estate lineage   # only these

Nothing here is mocked. The tool starts a Prama server of its own on a free
port with a throwaway database, runs the case studies against it through the
SDK exactly as a user would (each study creates its own estate), then signs in
to the console in headless Chromium and photographs the pages. So a screenshot
shows what the product does with the studies' fabricated banking data today,
and re-running this after a UI change refreshes every picture in the docs.

Needs the ``audit`` extra (Playwright) and an installed Google Chrome, which it
drives as the accessibility audit (tests/web/test_axe.py) does.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "assets" / "screenshots"
BIN = Path(sys.executable).parent
ADMIN, PASSWORD = "admin", "prama-dev-admin"
#: What the admin's password becomes once seeding is done, as an operator would
#: change it: otherwise every picture carries the default-password banner.
CHANGED = "screenshots-only-password-0123"
VIEWPORT = {"width": 1360, "height": 860}


@dataclass(frozen=True)
class Shot:
    """One picture: which study's estate it is taken in, and what page."""

    name: str
    study: str
    path: str
    #: Photograph the whole scrolled page, not just the first screen.
    full: bool = False
    #: Clicked before the picture, for a page whose interesting state is one click away.
    click: str = ""


#: The studies each estate comes from. Run once each; their estates persist.
STUDIES = {
    "trading": "01-trading-book-sqlite",
    "mixed": "03-mixed-estate",
    "delegates": "05-dq-delegates",
    "close": "06-month-end-close",
    "governance": "07-metadata-governance",
    "code": "08-code-to-impact",
}

#: Paths with ``{dataset}`` or ``{recon}`` are filled from the estate at run time.
SHOTS = (
    Shot("landing", "", "/"),
    Shot("estate", "mixed", "/estate"),
    Shot("estate-dataset", "mixed", "/estate/{dataset}", full=True),
    Shot("estate-gaps", "mixed", "/estate/gaps"),
    Shot("declarations", "mixed", "/declarations"),
    Shot("relationships", "mixed", "/relationships"),
    Shot("proposals", "trading", "/proposals"),
    Shot("controls", "trading", "/controls"),
    Shot("control-studio", "trading", "/controls/studio"),
    Shot("evidence", "trading", "/evidence"),
    Shot("incidents", "trading", "/incidents"),
    Shot("scorecards", "trading", "/scorecards"),
    Shot("reports", "trading", "/reports"),
    Shot("schedule", "trading", "/schedule"),
    Shot("reconciliation", "close", "/reconciliation/{recon}", full=True),
    Shot("metadata", "governance", "/metadata"),
    Shot("glossary", "governance", "/glossary"),
    Shot("queue", "governance", "/queue"),
    Shot("lineage", "code", "/lineage"),
    Shot("code", "code", "/code"),
    Shot("delegates", "delegates", "/delegates"),
    Shot("agents", "delegates", "/agents"),
    Shot("models", "trading", "/models"),
    Shot("admin-users", "trading", "/admin/users"),
    Shot("api-keys", "trading", "/account/keys"),
    Shot("help", "trading", "/help"),
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _server(work: Path) -> tuple[subprocess.Popen[bytes], str]:
    """A server from the shipped configuration, on a fresh database and a free port."""
    port = _free_port()
    config = work / "application.yaml"
    config.write_text((ROOT / "config" / "application.yaml").read_text(encoding="utf-8"))
    (work / "application.local.yaml").write_text(
        "security:\n  session_secret: screenshots-only-not-a-real-secret-0123456789\n"
        "  cookies_https_only: false\n"
        f"server:\n  host: 127.0.0.1\n  port: {port}\n"
        f"database:\n  sqlite:\n    path: {work / 'prama.db'}\n  schema_dir: {ROOT / 'schema'}\n"
        f"runs:\n  roots: [{ROOT / 'case-studies'}]\n"
        "logging:\n  level: WARNING\n",
        encoding="utf-8",
    )
    prama = [str(BIN / "prama"), "--config", str(config)]
    subprocess.run([*prama, "db", "init"], check=True, capture_output=True, cwd=ROOT)
    log = (work / "server.log").open("wb")
    process = subprocess.Popen([*prama, "serve"], stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 90
    while True:
        try:
            if httpx.get(url + "/livez", timeout=1).status_code == 200:
                return process, url
        except httpx.TransportError:
            pass
        if process.poll() is not None or time.monotonic() > deadline:
            raise SystemExit("the server did not start:\n" + (work / "server.log").read_text())
        time.sleep(0.3)


def _run_study(folder: str, url: str) -> str:
    """Run one case study against ``url``; return the slug of the estate it created."""
    study = ROOT / "case-studies" / folder
    done = subprocess.run(
        [sys.executable, "run.py", "--url", url, "--username", ADMIN, "--password", PASSWORD],
        cwd=study,
        capture_output=True,
        text=True,
        timeout=900,
    )
    found = re.search(r"This run's estate: (\S+)", done.stdout)
    if done.returncode != 0 or not found:
        raise SystemExit(
            f"case study {folder} failed:\n{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
        )
    return found.group(1)


#: Where to find the link a templated path stands for, and what the link looks like.
_LINKS = {
    "{dataset}": (
        ("/estate", "/estate/gaps", "/declarations"),
        re.compile(r"^/estate/[0-9A-HJKMNP-TV-Z]{26}$"),
    ),
}


def _reconciliation(url: str, slug: str) -> str:
    """The break workbench of the estate's first reconciliation, found through the SDK.

    Through the SDK because no console page links to the workbench yet.
    """
    import prama_sdk

    client = prama_sdk.connect(url, username=ADMIN, password=PASSWORD, tenant=slug)
    try:
        listed = client.reconciliation.list().get("reconciliations") or []
    finally:
        client.close()
    if not listed:
        raise SystemExit(f"the estate {slug} has no reconciliation")
    return f"/reconciliation/{listed[0]['definition']}"


def _change_password(url: str, slugs: list[str]) -> None:
    """In every estate: each one's admin is its own principal, with its own password."""
    import prama_sdk

    for slug in slugs:
        client = prama_sdk.connect(url, username=ADMIN, password=PASSWORD, tenant=slug)
        try:
            client.account.change_password(PASSWORD, CHANGED)
        finally:
            client.close()


def _fill(path: str, url: str, page: object) -> str:
    """Resolve ``{dataset}`` by following the console's own links."""
    for token, (pages, shape) in _LINKS.items():
        if token not in path:
            continue
        for where in pages:
            page.goto(url + where)  # type: ignore[attr-defined]
            page.wait_for_load_state("networkidle")  # type: ignore[attr-defined]
            hrefs = page.eval_on_selector_all(  # type: ignore[attr-defined]
                "a[href]", "els => els.map(e => e.getAttribute('href'))"
            )
            found = next((h for h in hrefs if h and shape.match(h)), None)
            if found:
                return found
        raise SystemExit(f"no link for {token} on {pages}")
    return path


def main(argv: list[str]) -> int:
    from playwright.sync_api import sync_playwright

    wanted = [s for s in SHOTS if not argv or s.name in argv]
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="prama-shots-") as scratch:
        process, url = _server(Path(scratch))
        try:
            estates = {
                key: _run_study(STUDIES[key], url)
                for key in sorted({s.study for s in wanted if s.study})
            }
            print("estates:", estates)
            # Before the browser signs in: an SDK sign-in as the same person
            # mid-session ends the console's session, and the page would be
            # photographed as the sign-in form.
            resolved = {
                s.name: _reconciliation(url, estates[s.study])
                for s in wanted
                if "{recon}" in s.path
            }
            _change_password(url, list(estates.values()))
            with sync_playwright() as play:
                # The installed Chrome, as the accessibility audit uses: no download.
                browser = play.chromium.launch(channel="chrome")
                for study in ["", *estates]:
                    page = browser.new_page(viewport=VIEWPORT, color_scheme="light")
                    if study:
                        page.goto(f"{url}/sign-in?tenant={estates[study]}")
                        page.fill("input[name=username]", ADMIN)
                        page.fill("input[name=password]", CHANGED)
                        tenant = page.locator("input[name=tenant]")
                        if tenant.count() and tenant.first.is_editable():
                            tenant.first.fill(estates[study])
                        page.locator("form button[type=submit]").first.click()
                        page.wait_for_load_state("networkidle")
                        if "/sign-in" in page.url:
                            raise SystemExit(f"could not sign in to {estates[study]}: {page.url}")
                    for shot in (s for s in wanted if s.study == study):
                        target = _fill(resolved.get(shot.name, shot.path), url, page)
                        page.goto(url + target)
                        page.wait_for_load_state("networkidle")
                        if shot.click:
                            page.click(shot.click)
                        page.wait_for_timeout(600)  # graphs settle their layout
                        page.screenshot(path=str(OUT / f"{shot.name}.png"), full_page=shot.full)
                        print(f"{shot.name:18} {target}")
                    page.close()
                browser.close()
        finally:
            process.terminate()
            process.wait(timeout=30)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
