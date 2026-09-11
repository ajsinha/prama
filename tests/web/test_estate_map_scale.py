"""How large an estate the map can actually draw.

`docs/09` claims 50,000 nodes at 60 fps pan/zoom. Nobody had measured it, and a
performance claim nobody has measured is the kind this repository is built not
to make — so this measures it, at several sizes, and reports the curve rather
than a pass or a fail.

**The graph is intercepted, not seeded.** The criterion is about the renderer,
so the browser is served a synthetic graph of N nodes instead of a database
holding N datasets. Seeding fifty thousand rows would measure SQLite.

**Frames are counted, not estimated.** `requestAnimationFrame` is sampled while
the camera is actually moving, because a still canvas reports sixty and means
nothing.

**The numbers are recorded, not asserted.** A hard threshold here would either
fail on a loaded laptop or pass on a fast one and prove neither. What *is*
asserted is the shape of the answer: that the page survives, that the honest
figure is written down, and that the documented claim matches what was measured.

Run it directly to see the curve::

    pytest -q tests/web/test_estate_map_scale.py -s

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import math
import multiprocessing
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from prama.api import create_app
from prama.core.config import Configuration, ConfigurationBuilder
from prama.db import Database

#: Sizes to measure. The last is the documented claim; the earlier ones exist so
#: a failure at the top says *where* it stopped being usable rather than only
#: that it did.
SIZES = (500, 2_000, 4_000, 6_000, 10_000, 50_000)

#: How long the page is given to draw before the attempt is called a failure.
#: Generous: this is a ceiling on patience, not a performance target. A map that
#: takes a minute to appear has already failed the person waiting for it.
RENDER_BUDGET_MS = 60_000

#: The budget is enforced by killing a **subprocess**, not by a timeout inside
#: the page. ``relax()`` blocks the browser's main thread, and every in-page
#: timer — including the one Playwright's ``wait_for_function`` polls on — is
#: starved while it does. An earlier version of this harness passed
#: ``timeout=120_000`` and then sat on a single page for **53 minutes** at 101%
#: CPU. An unenforceable budget is not a budget.
KILL_GRACE_SECONDS = 20

#: Where the measured curve is written, so the claim in docs/09 has a number
#: behind it that somebody can re-run.
RESULTS = Path(__file__).parent / "estate-map-scale.json"


def _playwright():
    return pytest.importorskip(
        "playwright.sync_api",
        reason="needs the audit extra: pip install -e '.[audit]'",
    )


@pytest.fixture(scope="module")
def server(tmp_path_factory) -> Iterator[str]:
    from prama.core.config.defaults import DEFAULTS

    root = tmp_path_factory.mktemp("mapscale")
    config: Configuration = (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(root / "scale.db")},
                    "schema_dir": str(Path(__file__).resolve().parents[2] / "schema"),
                    "verify_on_start": True,
                },
                "security": {
                    "session_secret": "map-scale-secret",
                    "cookies_https_only": False,
                },
                "web": {"enabled": True},
            },
            name="mapscale",
        )
        .build()
    )
    import asyncio

    async def _tenant() -> str:
        database_ = Database.from_config(config)
        database_.initialise(applied_by="map-scale")
        await database_.start()
        try:
            async with database_.unit_of_work() as uow:
                tenant = uow.tenants.create(slug="scale-bank", display_name="Scale Bank")
                await uow.flush()
                return str(tenant.id)
        finally:
            await database_.stop()

    tenant_id = asyncio.run(_tenant())
    config = (
        ConfigurationBuilder()
        .with_defaults(config.raw())
        .with_mapping({"tenancy": {"default_tenant": tenant_id}}, name="scale-tenant")
        .build()
    )
    app = create_app(config, database=Database.from_config(config))
    server_ = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server_.run, daemon=True)
    thread.start()
    while not server_.started:
        if not thread.is_alive():  # pragma: no cover - the server failed to boot
            raise RuntimeError("the console did not start")
    port = server_.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server_.should_exit = True
    thread.join(timeout=10)


def synthetic_graph(nodes: int) -> dict:
    """A graph of the shape a real estate has.

    Edges at roughly 1.4 per node and clustered rather than uniform, because a
    layout's cost depends on the structure and a uniform random graph is the
    easy case.
    """
    tiers = ("tier_1", "tier_2", "tier_3", "tier_4")
    payload_nodes = [
        {
            "key": f"ds-{i}",
            "attributes": {
                "label": f"dataset_{i}",
                "criticality": tiers[i % 4],
                "bound": i % 3 != 0,
                "complete": i % 5 != 0,
                "x": math.cos(i) * 100,
                "y": math.sin(i) * 100,
                "size": 3,
                "color": "#4C6EF5",
            },
        }
        for i in range(nodes)
    ]
    edges = []
    for i in range(nodes):
        for offset in (1, 7):
            target = (i + offset) % nodes
            if target != i:
                edges.append(
                    {
                        "key": f"e-{i}-{offset}",
                        "source": f"ds-{i}",
                        "target": f"ds-{target}",
                        "attributes": {"declared": offset == 1},
                    }
                )
    return {"nodes": payload_nodes, "edges": edges[: int(nodes * 1.4)]}


def _probe(base: str, nodes: int, sink) -> None:  # pragma: no cover - child process
    """Measure one size, in a process of its own so it can be killed.

    Runs in a subprocess deliberately: see ``KILL_GRACE_SECONDS``.
    """
    from playwright.sync_api import sync_playwright

    result: dict = {"nodes": nodes}
    graph = json.dumps(synthetic_graph(nodes))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route(
                "**/estate/graph.json*",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body=graph
                ),
            )
            page.goto(f"{base}/estate", wait_until="domcontentloaded")
            # The status line is written on the last statement of the success
            # path, after relax() and after the Sigma constructor. Nothing
            # earlier proves a graph of this size reached the screen: an
            # earlier version waited on `canvas.width > 0`, which Sigma sets
            # before it draws, and reported 10,000 nodes in 22 ms — faster than
            # it reported 500.
            page.wait_for_function(
                "() => { const s = document.getElementById('map-status');"
                " return s && /\\d+ datasets/.test(s.textContent || ''); }",
                timeout=RENDER_BUDGET_MS,
            )
            # Time since navigation start, read from inside the page. Not a
            # delta between two `page.evaluate` calls: an evaluate cannot run
            # while the main thread is blocked either, so the "start" reading
            # is taken *after* the blocking layout and the delta comes out as
            # 22 ms for a graph that takes seconds. Both earlier versions of
            # this line were wrong in that direction — flattering, and wrong.
            result["render_ms"] = round(page.evaluate("() => performance.now()"))
            status = page.evaluate("() => document.getElementById('map-status').textContent")
            result["counted"] = int(status.split()[0])
            frames = page.evaluate(
                """() => new Promise((resolve) => {
                     let count = 0;
                     const start = performance.now();
                     const el = document.querySelector('#estate-map');
                     let step = 0;
                     function tick(now) {
                       count += 1;
                       step += 1;
                       if (el) {
                         el.dispatchEvent(new WheelEvent('wheel', {
                           deltaY: step % 2 ? 60 : -60, bubbles: true,
                         }));
                       }
                       if (now - start < 2000) { requestAnimationFrame(tick); }
                       else { resolve({ frames: count, elapsed: now - start }); }
                     }
                     requestAnimationFrame(tick);
                   })"""
            )
            result["fps"] = round(frames["frames"] / (frames["elapsed"] / 1000), 1)
            # The measurement has to prove it measured this size. If the route
            # interception did not take, the page drew the real (empty) estate
            # and every number above is about a different graph.
            result["drew"] = result["counted"] == nodes
            if not result["drew"]:
                result["failure"] = (
                    f"the page reported {result['counted']} nodes, not {nodes}; "
                    "the interception did not take, so this is not a measurement of this size"
                )
            page.close()
            browser.close()
    except Exception as exc:
        result["drew"] = False
        result["failure"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    sink.put(result)


def measure(base: str, nodes: int) -> dict:
    """Draw a graph of `nodes` and report what happened, or kill it trying."""
    ctx = multiprocessing.get_context("spawn")
    sink = ctx.Queue()
    child = ctx.Process(target=_probe, args=(base, nodes, sink), daemon=True)
    child.start()
    child.join(RENDER_BUDGET_MS / 1000 + KILL_GRACE_SECONDS)
    if child.is_alive():
        child.kill()
        child.join(10)
        return {
            "nodes": nodes,
            "drew": False,
            "failure": (
                f"the page did not draw within {RENDER_BUDGET_MS // 1000}s and had to be "
                "killed — the browser's main thread was still blocked, so the page was "
                "not merely slow, it was unresponsive"
            ),
        }
    try:
        return sink.get_nowait()
    except Exception:
        return {"nodes": nodes, "drew": False, "failure": "the probe died without reporting"}


@pytest.fixture(scope="module")
def curve(server: str) -> list[dict]:
    _playwright()  # skip loudly, and by name, if the audit extra is not installed
    measured = []
    for size in SIZES:
        outcome = measure(server, size)
        measured.append(outcome)
        print(f"\n  estate map · {size:>6,} nodes → {outcome}")
        if not outcome["drew"]:
            # Stop climbing. Everything above this fails too, and spending four
            # more minutes proving it tells nobody anything.
            break
    RESULTS.write_text(json.dumps(measured, indent=2) + "\n", encoding="utf-8")
    return measured


class TestTheMapAtScale:
    def test_it_draws_the_estates_the_product_is_sold_for(self, curve) -> None:
        """Two thousand datasets is a large bank's declared estate, and the code
        itself says the renderer exists because SVG stops being usable around
        eight hundred. Failing here would be failing at the advertised job."""
        for outcome in curve:
            if outcome["nodes"] <= 2_000:
                assert outcome["drew"], outcome

    def test_the_curve_is_written_down(self, curve) -> None:
        """A measurement nobody recorded is an anecdote. This file is what the
        claim in docs/09 points at."""
        assert RESULTS.exists()
        recorded = json.loads(RESULTS.read_text(encoding="utf-8"))
        assert [r["nodes"] for r in recorded] == [c["nodes"] for c in curve]

    def test_the_documented_claim_matches_the_measurement(self, curve) -> None:
        """The point of the exercise.

        `docs/09` claimed 50,000 nodes at 60 fps. If the measurement supports
        it the document may say so; if it does not, the document must say what
        was actually achieved. This test fails when the two disagree, whichever
        way — a claim above the measurement is an overstatement, and one below
        it is a product being sold short.
        """
        largest = max((c for c in curve if c["drew"]), key=lambda c: c["nodes"], default=None)
        document = (
            Path(__file__).resolve().parents[2] / "docs" / "09-connectivity-and-formats.md"
        ).read_text(encoding="utf-8")

        if largest is None:
            pytest.fail("the map drew nothing at any size, which is a defect not a limit")

        claimed = f"{largest['nodes']:,}"
        assert claimed in document or "estate map" not in document.lower(), (
            f"the map was measured at {claimed} nodes and the document does not "
            "say so. Update the claim to the measurement."
        )
